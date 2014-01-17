#!/usr/bin/python
"""
Library for basic acceptance tests
Author: Martin Simon <msimon@redhat.com>
Version: 2 (2012-04-13)
"""
import sys
import time
import os
import re

from dogtail.utils import isA11yEnabled, enableA11y, GnomeShell
if isA11yEnabled() is False:
    print("gnome-apps-helper: Enabling a11y")
    enableA11y(True)
    if isA11yEnabled() is False:
        time.sleep(5)
        print("Warning: second attempt to enable a11y")

from dogtail.utils import run as utilsRun
from dogtail.tree import root
from dogtail.tree import SearchError
from dogtail import predicate
from dogtail.rawinput import keyCombo, click, typeText, absoluteMotion, pressKey
from subprocess import Popen, PIPE
from iniparse import ConfigParser
import traceback

# we must kill this vermin before we start at all
Popen("pkill gnome-initital", shell=True).wait()

def getMiniaturesPosition(name):
    """Get a position of miniature on Overview"""
    miniatures = []

    over = root.application('gnome-shell').child(name='Overview')
    mini = over.parent.children[-1]
    if mini == over:
        print("Overview is not active")
        return miniatures
    widgets = mini.findChildren(
        predicate.GenericPredicate(name=name, roleName='label'))

    for widget in widgets:
        (x, y) = widget.position
        (a, b) = widget.size
        miniatures.append((x + a / 2, y + b / 2 - 100))
    return miniatures


def getDashIconPosition(name):
    """Get a position of miniature on Overview"""
    over = root.application('gnome-shell').child(name='Overview')
    button = over[2].child(name=name)
    (x, y) = button.position
    (a, b) = button.size
    return (x + a / 2, y + b / 2)

def clickFocus(frame, maximize=False):
    """ Will focus on the window by clicking in the middle of its frame's titlebar.
    Input a frame or dialog, will try to get its coords and click the titlebar"""
    try:
        coordinates = (frame.position[0]+frame.size[0]/2, frame.position[1]+5)
        if maximize is False:
            click(coordinates[0], coordinates[1])
        else:  # a doubleClick to maximize as well
            doubleClick(coordinates[0], coordinates[1])
    except:
        print("Warning: Could not clickFocus() at the app frame")
        return False

def isProcessRunning(process):
    '''
    Gives true if process can be greped out of the full ps dump
    '''
    s = Popen(["ps", "axw"], stdout=PIPE)
    for x in s.stdout:
        if re.search(process, x):
            return True
    return False


class App(object):

    """
    Does all basic events with app
    """

    def __init__(
        self, appName, critical=None, shortcut='<Control><Q>', desktopFileName=None, a11yAppName=None, quitButton=None, timeout=5,
            forceKill=True, parameters='', polkit=False, recordVideo=True):
        """
        Initialize object App
        appName     command to run the app
        critical    what's the function we check? {start,quit}
        shortcut    default quit shortcut
        timeout     timeout for starting and shuting down the app
        forceKill   is the app supposed to be kill before/after test?
        parameters  has the app any params needed to start? (only for startViaCommand)
        desktopFileName = name of the desktop file if other than appName (without .desktop extension)
        """
        self.appCommand = appName
        self.shortcut = shortcut
        self.timeout = timeout
        self.forceKill = forceKill
        self.critical = critical
        self.quitButton = quitButton
        # the result remains false until the correct result is verified
        self.result = False
        self.updateCorePattern()
        self.parameters = parameters
        self.internCommand = self.appCommand.lower()
        self.polkit = polkit
        self.polkitPass = 'redhat'
        self.a11yAppName = a11yAppName
        self.recordVideo = recordVideo

        if desktopFileName is None:
            desktopFileName = self.appCommand
        self.desktopFileName = desktopFileName

        # a way of overcoming overview autospawn when mouse in 1,1 from start
        pressKey('Esc')
        absoluteMotion(100, 100, 2)
        # attempt to make a recording of the test
        if self.recordVideo:
            keyCombo('<Control><Alt><Shift>R')

    def parseDesktopFile(self):
        """
        Getting all necessary data from *.dektop file of the app
        """
        cmd = "rpm -qlf $(which %s)" % self.appCommand
        cmd += '| grep "^/usr/share/applications/.*%s.desktop$"' % self.desktopFileName
        proc = Popen(cmd, shell=True, stdout=PIPE)
        # !HAVE TO check if the command and its desktop file exist
        if proc.wait() != 0:
            raise Exception("*.desktop file of the app not found")
        output = proc.communicate()[0].rstrip()
        self.desktopConfig = ConfigParser()
        self.desktopConfig.read(output)

    def end(self):
        """
        Ends the test with correct return value
        """
        if self.recordVideo:
            keyCombo('<Control><Alt><Shift>R')
        time.sleep(2)
        if not isProcessRunning('gnome-shell') or isProcessRunning('gnome-shell --mode=gdm'):
            print ("Error: gnome-shell/Xorg crashed during or after the test!")
            self.result = False

        if self.result:
            print("PASS")
            sys.exit(0)
        else:
            print("FAIL")
            sys.exit(1)

    def updateResult(self, result):
        self.result = result

    def getName(self):
        return self.desktopConfig.get('Desktop Entry', 'name')

    def getExec(self):
        try:
            return (
                self.desktopConfig.get(
                    'Desktop Entry',
                    'exec').split()[0].split('/')[-1]
            )
        except ConfigParser.NoOptionError:
            return self.getName()

    def getCategories(self):
        return self.desktopConfig.get('Desktop Entry', 'categories')

    def getMenuGroups(self):
        """
        Convert group list to the one correct menu group
        """
        groupsList = self.getCategories().split(';')
        groupsList.reverse()
        groupConversionDict = {
            'Accessibility': 'Universal Access',
            'System': 'System Tools',
            'Development': 'Programming',
            'Network': 'Internet',
            'Office': 'Office',
            'Graphics': 'Graphics',
            'Game': 'Games',
            'Education': 'Education',
            'Utility': 'Accessories',
            'AudioVideo': 'Sound &amp; Video'
        }
        for i in groupsList:
            if i in groupConversionDict:
                return groupConversionDict[i]

    def isRunning(self):
        """
        Is the app running?
        """
        if self.a11yAppName is None:
            self.a11yAppName = self.internCommand

        def getApp():
            try:
                #from dogtail.tree import root
                apps = root.applications()
            except:
                traceback.print_exc(file=sys.stdout)
                time.sleep(4)
                #from dogtail.tree import root
                try:
                    app = root.application(self.a11yAppName)
                    return app
                except SearchError:
                    return None

            for i in apps:
                if i.name.lower() == self.a11yAppName:
                    return i
            return None

        print("*** Checking if '%s' is running" % self.a11yAppName)
        try:  # should the a11y app reload due to start screen (i.e. gimp)
            app = getApp()
        except:
            time.sleep(5)
            app = getApp()
        if app is None or len(app) == 0:
            print("*** The app '%s' is not running" % self.a11yAppName)
            return False
        else:
            print("*** The app '%s' is running" % self.a11yAppName)
            return True

    def kill(self):
        """
        Kill the app via 'killall'
        """
        if self.recordVideo:
            keyCombo('<Control><Alt><Shift>R')
        print("*** Killing all '%s' instances" % self.appCommand)
        return Popen("pkill " + self.appCommand, shell=True).wait()

    def updateCorePattern(self):
        """
        Update string in /proc/sys/kernel/core_pattern to catch
        possible return code
        """
        Popen("sudo rm -rf /tmp/cores", shell=True).wait()
        Popen("mkdir /tmp/cores", shell=True).wait()
        Popen("chmod a+rwx /tmp/cores", shell=True).wait()
        Popen(
            "echo \"/tmp/cores/core.%e.%s.%p\" | sudo tee /proc/sys/kernel/core_pattern",
            shell=True).wait()

    def existsCoreDump(self):
        """
        Check if there is core dump created
        """
        dirPath = "/tmp/cores/"
        files = os.listdir(dirPath)
        regexp = "core\.%s\.[0-9]{1,3}\.[0-9]*" % self.appCommand
        for f in files:
            if re.match(regexp, f):
                return int(f.split(".")[2])
        return 0

    def startViaMenu(self, throughCategories=False):
        """
        Start the app via Gnome Shell menu
        """
        internCritical = (self.critical == 'start')

        self.parseDesktopFile()

        # check if the app is running
        if self.forceKill and self.isRunning():
            self.kill()
            time.sleep(2)
            if self.isRunning():
                if internCritical:
                    self.updateResult(False)
                print("!!! The app is running but it shouldn't be")
                return False
            else:
                print("*** The app has been killed succesfully")

        try:
            # panel button Activities
            gnomeShell = root.application('gnome-shell')
            pressKey('Super_L')
            time.sleep(6)  # time for overview to appear

            if throughCategories:
                # menu Applications
                x, y = getDashIconPosition('Show Applications')
                absoluteMotion(x, y)
                time.sleep(1)
                click(x, y)
                time.sleep(4)  # time for all the oversized app icons to appear

                # submenu that contains the app
                submenu = gnomeShell.child(
                    name=self.getMenuGroups(), roleName='list item')
                submenu.click()
                time.sleep(4)

                # the app itself
                app = gnomeShell.child(
                    name=self.getName(), roleName='label')
                app.click()
            else:
                typeText(self.getName())
                time.sleep(2)
                pressKey('Enter')

            # if there is a polkit
            if self.polkit:
                time.sleep(3)
                typeText(self.polkitPass)
                keyCombo('<Enter>')

            time.sleep(self.timeout)

            if self.isRunning():
                print("*** The app started successfully")
                if internCritical:
                    self.updateResult(True)
                return True
            else:
                print("!!! The app is not running but it should be")
                if internCritical:
                    self.updateResult(False)
                return False
        except SearchError:
            print("!!! Lookup error while passing the path")
            if internCritical:
                self.updateResult(False)
            return False

    def startViaCommand(self):
        """
        Start the app via command
        """
        internCritical = (self.critical == 'start')
        if self.forceKill and self.isRunning():
            self.kill()
            time.sleep(2)
            if self.isRunning():
                if internCritical:
                    self.updateResult(False)
                print("!!! The app is running but it shouldn't be")
                return False
            else:
                print("*** The app has been killed succesfully")

        returnValue = 0
        command = "%s %s" % (self.appCommand, self.parameters)
        returnValue = utilsRun(command, timeout=10, dumb=True)

        # if there is a polkit
        if self.polkit:
            time.sleep(3)
            typeText(self.polkitPass)
            keyCombo('<Enter>')

        time.sleep(self.timeout)

        # check the returned values
        if returnValue is None:
            if internCritical:
                self.updateResult(False)
            print("!!! The app command could not be found")
            return False
        else:
            if self.isRunning():
                if internCritical:
                    self.updateResult(True)
                print("*** The app started successfully")
                return True
            else:
                if internCritical:
                    self.updateResult(False)
                print("!!! The app did not started despite the fact that the command was found")
                return False

    def closeViaShortcut(self):
        """
        Close the app via shortcut
        """
        internCritical = (self.critical == 'quit')

        if not self.isRunning():
            if internCritical:
                self.updateResult(False)
            print("!!! The app does not seem to be running")
            return False

        keyCombo(self.shortcut)
        time.sleep(self.timeout)

        if self.isRunning():
            if self.forceKill:
                self.kill()
            if internCritical:
                self.updateResult(False)
            print("!!! The app is running but it shouldn't be")
            return False
        else:
            if self.existsCoreDump() != 0:
                if internCritical:
                    self.updateResult(False)
                print("!!! The app closed with core dump created. Signal %d" % self.existsCoreDump())
                return False
            if internCritical:
                self.updateResult(True)
            print("*** The app was successfully closed")
            return True

    def closeViaMenu(self):
        """
        Close app via menu button
        """
        internCritical = (self.critical == 'quit')

        if not self.isRunning():
            if internCritical:
                self.updateResult(False)
            print("!!! The app does not seem to be running")
            return False

        # try to bind the menu and the button
        try:
            firstSubmenu = self.getMenuNth(0)
            firstSubmenu.click()
            length = len(firstSubmenu.children)
            closeButton = firstSubmenu.children[length - 1]
            if self.quitButton is None:
                while re.search('(Close|Quit|Exit)', closeButton.name) is None:
                    length = length - 1
                    closeButton = firstSubmenu.children[length]
                    if length < 0:
                        if internCritical:
                            self.updateResult(False)
                        print("!!! The app quit button coldn't be found")
                        return False
            else:
                closeButton = firstSubmenu.child(self.quitButton)
        except SearchError:
            if internCritical:
                self.updateResult(False)
            print("!!! The app menu bar or the quit button could'n be found")
            if self.forceKill:
                self.kill()
            return False

        time.sleep(2)  # timeout until menu appear
        print("*** Trying to click to '%s'" % closeButton)
        closeButton.click()
        time.sleep(self.timeout)

        if self.isRunning():
            if self.forceKill:
                self.kill()
            if internCritical:
                self.updateResult(False)
            print("!!! The app is running but it shouldn't be")
            return False
        else:
            if self.existsCoreDump() != 0:
                if internCritical:
                    self.updateResult(False)
                print("!!! The app closed with core dump created. Signal %d" % self.existsCoreDump())
                return False
            if internCritical:
                self.updateResult(True)
            print("*** The app was successfully closed")
            return True

    def getMenuNamed(self, menuName):
        """
        Return submenu with name specified with 'menuName'
        """
        # bind to the right app
        if self.a11yAppName is None:
            self.a11yAppName = self.internCommand
        app = root
        apps = root.applications()
        for i in apps:
            if i.name.lower() == self.a11yAppName:
                app = i
                break

        # try to bind the menu and the button
        try:
            appMenu = app.child(roleName='menu bar')
            return appMenu.child(name=menuName)
        except:
            return None

    def getMenuNth(self, nth):
        """
        Return nth submenu
        """
        # bind to the right app
        if self.a11yAppName is None:
            self.a11yAppName = self.internCommand
        app = root
        apps = root.applications()
        for i in apps:
            if i.name.lower() == self.a11yAppName:
                app = i
                break

        # try to bind the menu and the button
        try:
            appMenu = app.child(roleName='menu bar')
            return appMenu.children[nth]
        except:
            return None

    def closeViaGnomePanel(self):
        """
        Close the app via menu at gnome-panel
        """
        internCritical = (self.critical == 'quit')

        self.parseDesktopFile()

        if not self.isRunning():
            if internCritical:
                self.updateResult(False)
            print("!!! The app does not seem to be running")
            return False

        print("*** Trying to click to '%s -> Quit'" % self.getName())
        shell = GnomeShell()
        shell.clickApplicationMenuItem(self.getName(), 'Quit')

        time.sleep(self.timeout)

        if self.isRunning():
            if self.forceKill:
                self.kill()
            if internCritical:
                self.updateResult(False)
            print("!!! The app is running but it shouldn't be")
            return False
        else:
            if self.existsCoreDump() != 0:
                if internCritical:
                    self.updateResult(False)
                print("!!! The app closed with core dump created. Signal %d" % self.existsCoreDump())
                return False
            if internCritical:
                self.updateResult(True)
            print("*** The app was successfully closed")
            return True
