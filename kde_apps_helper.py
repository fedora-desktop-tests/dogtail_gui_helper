#!/usr/bin/python

"""
 Module with helper class to create a basis for writing tests for KDE/QT
 apps or even GTK apps under KDE. All is present for basic acceptance,
 inherit from the KdeApp class to make a helper for specific KDE app.
"""

import sys, time, os, re, pwd, traceback

from dogtail.utils import isA11yEnabled, enableA11y, screenshot
if isA11yEnabled() is False:
    print("kde-apps-helper: Enabling a11y")
    enableA11y(True)
    if isA11yEnabled() is False:
        time.sleep(5)
        print("Warning: second attempt to enable a11y")

from dogtail.utils import run as appRun
from time import sleep
from dogtail.tree import root, SearchError
from dogtail.rawinput import keyCombo,click,doubleClick,typeText,pressKey
from subprocess import Popen,PIPE
from gi.repository import Gdk

stdout_prefix = '>>> >>> '
stderr_prefix = '!!! >>> '

# pretty print a standard message
def printOut(message):
    sys.stdout.write('%s %s\n' % (stdout_prefix, message))

# pretty print a message to stderr
def printError(message):
    sys.stderr.write('%s %s\n' % (stderr_prefix, message))

# returns integer representing pixel height of the screen
def getScreenHeight():
    return Gdk.Display.get_default().get_default_screen().get_root_window().get_height()

def printException():
    printOut("-- FAIL due to exception:")
    printOut('-'*60)
    traceback.print_exc(file=sys.stdout)
    printOut('-'*60)

class KdeApp(object):

    corner_distance = 10
    splashscreen_delay = 15 # time to wait for everything to load still under splash-screen

    def __init__(self, command, appname=None, quit_shortcut='<Control><Q>', test=None):
        """Inits the class instance with the information about a specific application

        @param command: a command to execute the app in terminal (without params! (use
        startViaCommand to do that))
        @param appname: a name of application as seen by a11y, only if different from command
        @param quit_shortcut:
        @param test: a name of the test to report to beaker, can be None
        """
        if appname is None:
            appname = command
        if test is None:
            self.test = appname
        self.command = command
        self.appname = appname
        self.test = test
        self.shortcut = quit_shortcut
        self.app = None
        self.updateCorePattern()

    def getHighestPid(self):
        """ Gets the highest pid of all application processes """
        pipe = Popen('pgrep %s' % self.command, shell=True, stdout=PIPE).stdout
        # returns the highest pgreped pid
        try:
            return int(pipe.read().split()[-1])
        except IndexError:
            return None

    def clickFocus(self, maximize=None):
        """ Will focus on the app by clicking in the middle of its window titlebar"""
        try:
            main_win = self.app.child(roleName='window', recursive=False)
            coordinates = (main_win.position[0]+main_win.size[0]/2, main_win.position[1]-10)
            if maximize is None:
                click(coordinates[0],coordinates[1])
            else: #a doubleClick to maximize as well
                doubleClick(coordinates[0],coordinates[1])
        except:
            printException()
            return False

    def startViaMenu(self):
        """ Will run the app through the standard application launcher """
        try:
            sleep(self.splashscreen_delay) # time before kwin starts up and the splash screen disappears
            height = Gdk.Display.get_default().get_default_screen().get_root_window().get_height()
            click(self.corner_distance,height - self.corner_distance)
            plasma = root.application('plasma-desktop')
            plasma.child(name='Search:', roleName='label').click()
            typeText(self.command)
            sleep(1)
            pressKey('enter')
            sleep(5)
        except:
            printException()
            return False
        self.__PID = self.getHighestPid()
        return self.checkRunning('Running %s via menu search' % self.appname)

    def startViaKRunner(self):
        """ Simulates running app through Run command interface (alt-F2...)"""
        try:
            sleep(self.splashscreen_delay) #
            os.system('krunner')
            sleep(1.5)
            typeText('%s' % self.command)
            sleep(2)
            pressKey('enter')
            sleep(5)
        except:
            printException()
            return False
        self.__PID = self.getHighestPid()
        return self.checkRunning('Running %s via menu Run Command Interface' % self.appname)

    def startViaCommand(self, params = '', timeout = 10):
        """ Directly executes the application, independent from the Desktop layout """
        try:
            if len(params) > 0:
                params = " " + params
            self.__PID = appRun(self.appname + params, timeout)
            sleep(5)
        except:
            printException()
            return False
        return self.checkRunning('Running %s via command' % self.appname)

    def checkRunning(self, message, terminate = False):
        """ Checks whether the application is running, will also
            see if it crashed and made a core dump; Will write
            a rhts result, thus serves as a test checkpoint"""
        result = terminate
        if self.isAccessible():
            printOut ('%s is running!' % self.appname)
            result = not terminate
            if terminate: self.kill()
        if self.isCoreDump() is not False:
            printError ('%s exited with code %d!' % (self.appname, self.isCoreDump()))
            result = False
        screenshot()
        self.writeResult(message, result)
        return result

    def closeViaMenu(self, menu='File', menuitem='Quit'):
        """ Does execute 'Quit' item in the main menu """
        try:
            if not self.checkRunning('check %s is running before closing' % self.appname, False):
                return False
            self.clickFocus()
            self.app.child(name=menu, roleName='menu item').click()
            sleep(1)
            self.app.child(name=menuitem, roleName='menu item').click()
            sleep(2)
        except:
            printException()
            return False
        return self.checkRunning('Quiting %s through menu' % self.appname, True)

    def closeViaShortcut(self):
        """ Exit the application through the predefined keyboard shortcut """
        try:
            if not self.checkRunning('check %s is running before closing' % self.appname, False):
                return False
            self.clickFocus()
            keyCombo(self.shortcut)
            sleep(2)
        except:
            printException()
            return False
        return self.checkRunning('Quiting %s through shortcut' % self.appname, True)

    def writeResult(self, description, result):
        """
        Write a test result on stdout and using rhts-report-result.

        @param description: Short description of executed test.
        @type description: String
        @param result: Result of the test.
        @type result: Boolean
        """
        if result:
            result = "PASS"
            printOut("%s: %s" % (description, result))
        else:
            result = "FAIL"
            printError("%s: %s" % (description, result))
        if pwd.getpwuid(os.getuid())[0] == 'test':
            subtestname = description.replace(' ', '-')
            log = '/dev/null'
            cmd = 'sudo rhts-report-result %s/%s %s %s' % (self.test, subtestname,
                                                            result, log)
            Popen(cmd, shell = True).wait()

    def getPid(self):
        return os.system('pidof %s |wc -w' % self.command)

    def isAccessible(self):
        """ Returns true if the application is visible under the AT-SPI
            root desktop """
        try:
            self.app = root.child(name=self.appname, roleName='application', retry=False, recursive=False)
            printOut("%s is accessible" % self.appname)
            sleep(1)
            return True
        except SearchError:
            printError("%s couldn't be found" % self.appname)
            return False

    def signal(self, signal):
        """ Sends a singal to the latest app process """
        if self.getHighestPid() == None:
            printError('%s cant be signaled!' % self.appname)
            return
        return Popen("kill -%d %d" % (signal, self.getHighestPid()), shell = True).wait()

    def terminate(self):
        """ Invoke sigterm on latest application process"""
        self.signal(15)
        sleep(1)
        result = True
        if self.getHighestPid() == self.__PID:
            printError ('%s did not terminate!' % self.appname)
            result = False
        self.writeResult('Terminating %s' % self.appname, result)

    def kill(self):
        """ 'There can be no discussion that you will end!' """
        self.signal(9)

    def updateCorePattern(self):
        """ Update string in /proc/sys/kernel/core_pattern to catch
        possible return code """
        Popen("rm -rf /tmp/cores", shell = True).wait()
        Popen("mkdir /tmp/cores", shell = True).wait()
        Popen("chmod a+rwx /tmp/cores", shell = True).wait()
        Popen("echo \"/tmp/cores/core.%e.%s.%p\" | sudo tee /proc/sys/kernel/core_pattern", shell = True).wait()

    def isCoreDump(self):
        """ Check if there is core dump created """
        dirPath = "/tmp/cores/"
        files = os.listdir(dirPath)
        regexp = "core\.%s\.[0-9]{1,3}\.[0-9]*" % self.command
        for f in files:
            if re.match(regexp, f):
                return int(f.split(".")[2])
        return False
