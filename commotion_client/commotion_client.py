#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Commotion_client

The main python script for implementing the commotion_client GUI.

Key componenets handled within:
 * singleApplication mode
 * cross instance messaging
 * creation of main GUI
 * command line argument parsing
 * translation
 * initial logging settings

"""

import sys
import argparse
import logging

from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4 import QtNetwork

from utils import logger
from GUI.main_window import MainWindow
#from controller import CommotionController #TODO Create Controller



def get_args():
    #Handle command line arguments
    arg_parser = argparse.ArgumentParser(description="Commotion Client")
    arg_parser.add_argument("-v", "--verbose",
                            help="Define the verbosity of the Commotion Client.",
                            type=int, choices=range(1, 6))
    arg_parser.add_argument("-l", "--logfile",
                            help="Choose a logfile for this instance")
    arg_parser.add_argument("-d", "--daemon", action="store_true",
                            help="Start the application in Daemon mode (no UI).")
    arg_parser.add_argument("-m", "--message",
                            help="Send a message to any existing Commotion Application")
    arg_parser.add_argument("-k", "--key",
                            help="Choose a unique application key for this Commotion Instance",
                            type=str)
    args = arg_parser.parse_args()
    parsed_args = {}
    parsed_args['message'] = args.message if args.message else False
    #TODO getConfig() #actually want to get this from commotion_config
    parsed_args['logLevel'] = args.verbose if args.verbose else 2
    #TODO change the logfile to be grabbed from the commotion config reader
    parsed_args['logFile'] = args.logfile if args.logfile else "temp/logfile.temp" 
    parsed_args['key'] = ['key'] if args.key else "commotionRocks" #TODO the key is PRIME easter-egg fodder
    parsed_args['status'] = "daemon" if args.daemon else False
    return parsed_args

#==================================
# Main Applicaiton Creator
#==================================

def main():
    """
    Function that handles command line arguments, translation, and creates the main application.
    """
    args = get_args()

    #Enable Logging
    log = logger.set_logging("commotion_client", args['logLevel'], args['logFile'])
    
    #Create Instance of Commotion Application
    app = CommotionClientApplication(args['key'], args['status'], sys.argv)

    #Enable Translations #TODO This code needs to be evaluated to ensure that it is pulling in correct translators
    locale = QtCore.QLocale.system().name()
    qt_translator = QtCore.QTranslator()
    if qt_translator.load("qt_"+locale, ":/"):
        app.installTranslator(qt_translator)
        app_translator = QtCore.QTranslator()
        if app_translator.load("imagechanger_"+locale, ":/"): #TODO This code needs to be evaluated to ensure that it syncs with any internationalized images
            app.installTranslator(app_translator)

    #check for existing application w/wo a message
    if app.is_running():
        if args['message']:
            #Checking for custom message
            msg = args['message']
            app.send_message(msg)
            log.info(app.translate("logs", "application is already running, sent following message: \n\"{0}\"".format(msg)))
        else:
            log.info(app.translate("logs", "application is already running. Application will be brought to foreground"))
            app.send_message("showMain")
        sys.exit(1)

    #initialize client (GUI, controller, etc)
    app.init_client()
        
    sys.exit(app.exec_())
    log.debug(app.translate("logs", "Shutting down"))


    
class SingleApplication(QtGui.QApplication):
    """
    Single application instance uses a key and shared memory to ensure that only one instance of the Commotion client is ever running at the same time.
    """

    def __init__(self, key, argv):
        super().__init__(argv)

        #set function logger
        self.log = logging.getLogger("commotion_client."+__name__)
        
        #Keep Track of main widgets, so as not to recreate them.
        self.main = False
        self.status_bar = False
        self.control_panel = False
        #Check for shared memory from other instances and if not created, create them.
        self._key = key
        self.shared_memory = QtCore.QSharedMemory(self)
        self.shared_memory.setKey(key)
        if self.shared_memory.attach():
            self._is_running = True
        else:
            self._is_running = False
            if not self.shared_memory.create(1):
                self.log.info(self.translate("logs", "Application shared memory already exists."))
                raise RuntimeError(self.shared_memory.errorString())
                
    def is_running(self):
        return self._is_running


class SingleApplicationWithMessaging(SingleApplication):
    """
    The interprocess messaging class for the Commotion Client. This class extends the single application to allow for instantiations of the Commotion Client to pass messages to the existing client if it is already running. When a second instance of a Commotion Client is run without a message specified it will reaise the earler clients main window to the front and then close itself.

    e.g:
    python3.3 CommotionClient.py --message "COMMAND"
    """
    
    def __init__(self, key, argv):
        super().__init__(key, argv)

        self._key = key
        self._timeout = 1000
        #create server to listen for messages
        self._server = QtNetwork.QLocalServer(self)
        #Connect to messageAvailable signal created by handle_message.
        self.connect(self, QtCore.SIGNAL('messageAvailable'), self.process_message)

        if not self.is_running():
            bytes.decode
            self._server.newConnection.connect(self.handle_message)
            self._server.listen(self._key)

    def handle_message(self):
        """
        Server side implementation of the messaging functions. This function waits for signals it receives and then emits a SIGNAL "messageAvailable" with the decoded message.
        
        (Emits a signal instead of just calling a function in case we decide we would like to allow other components or extensions to listen for messages from new instances.)
        """
        socket = self._server.nextPendingConnection()
        if socket.waitForReadyRead(self._timeout):
            self.emit(QtCore.SIGNAL("messageAvailable"), bytes(socket.readAll().data()).decode('utf-8'))
            socket.disconnectFromServer()
            self.log.debug(self.translate("logs", "message received and emitted in a messageAvailable signal"))
        else:
            print("socket error")
            self.log.error(socket.errorString())

    def send_message(self, message):
        """
        Message sending function. Connected to local socket specified by shared key and if successful writes the message to it and returns.
        """
        if self.is_running():
            socket = QtNetwork.QLocalSocket(self)
            socket.connectToServer(self._key, QtCore.QIODevice.WriteOnly)
            if not socket.waitForConnected(self._timeout):
                self.log.error(socket.errorString())
                return False
            socket.write(str(message).encode("utf-8"))
            if not socket.waitForBytesWritten(self._timeout):
                self.log.error(socket.errorString())
                return False
            socket.disconnectFromServer()
            return True
        self.log.debug(self.translate("logs", "Attempted to send message when commotion client application was not currently running."))
        return False

    def process_message(self, message):
        """
        Process which processes messages an app receives and takes actions on valid requests.
        """
        self.log.debug(self.translate("logs", "Applicaiton received a message {0}, but does not have a message parser to handle it.").format(message))

        
class CommotionClientApplication(SingleApplicationWithMessaging):
    """
    The final layer of the class onion that is the Commotion client. This class includes functions to enable the sub-processes and modules of the Commotion Client (GUI's and controllers). 
    """
    
    def __init__(self, key, status, argv):
        super().__init__(key, argv)
        #Set Application and Organization Information
        self.setOrganizationName("The Open Technology Institute")
        self.setOrganizationDomain("commotionwireless.net")
        self.setApplicationName(self.translate("main", "Commotion Client")) #special translation case since we are outside of the main application
        self.setWindowIcon(QtGui.QIcon(":logo48.png"))
        self.setApplicationVersion("1.0") #TODO Generate this on build
        self.status = status
        self.controller = False
        self.main = False


    def init_client(self):
        """
        Start up client using current status to determine run_level.
        """
        try:
            if not self.status:
                self.start_full()
            elif self.status == "daemon":
                self.start_daemon()
        except Exception as _excp:
            self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not fully initialize applicaiton. Application must be halted."))
            self.log.debug(_excp, exc_info=1)
            sys.exit(1)

    def stop_client(self, force_close=None):
        """
        Stops all running client processes.

        @param force_close bool Whole application exit if clean close fails. See: close_controller() & close_main_window()
        """
        try:
            self.close_main_window(force_close)
            self.close_controller(force_close)
        except Exception as _excp:
            if force_close:
                self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not cleanly close client. Application must be halted."))
                self.log.debug(_excp, exc_info=1)
                sys.exit(1)
            else:
                self.log.error(QtCore.QCoreApplication.translate("logs", "Client could not be closed."))
                self.log.info(QtCore.QCoreApplication.translate("logs", "It is reccomended that you restart the application."))
                self.log.debug(_excp, exc_info=1)

    def restart_client(self, force_close=None):
        """
        Restarts the entire client stack according to current application status.

        @param force_close bool Whole application exit if clean close fails. See: close_controller() & close_main_window()
        """
        try:
            self.stop_client(force_close)
            self.init_client()
        except Exception as _excp:
            if force_close:
                self.log.error(QtCore.QCoreApplication.translate("logs", "Client could not be restarted. Applicaiton will now be halted"))
                self.log.debug(_excp, exc_info=1)
                sys.exit(1)
            else:
                self.log.error(QtCore.QCoreApplication.translate("logs", "Client could not be restarted."))
                self.log.info(QtCore.QCoreApplication.translate("logs", "It is reccomended that you restart the application."))
                self.log.debug(_excp, exc_info=1)
                raise
                
    def create_main_window(self):
        """
        Will create a new main window or return existing main window if one is already created.
        """
        if self.main:
            self.log.debug(QtCore.QCoreApplication.translate("logs", "New window requested when one already exists. Returning existing main window."))
            self.log.info(QtCore.QCoreApplication.translate("logs", "If you would like to close the main window and re-open it please call close_main_window() first."))
            return self.main
        try:
            _main = MainWindow()
        except Exception as _excp:
            self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not create Main Window. Application must be halted."))
            self.log.debug(_excp, exc_info=1)
            raise
        else:
            return _main

    def hide_main_window(self, force=None, errors=None):
        """
        Attempts to hide the main window without closing the task-bar.

        @param force bool Force window reset if hiding is unsuccessful.
        @param errors If set to "strict" errors found will be raised before returning the boolean result.
        @return bool Return True if successful and false is unsuccessful.
        """
        try:
            self.main.exitOnClose = False
            self.main.close()
        except Exception as _excp:
            self.log.error(QtCore.QCoreApplication.translate("logs", "Could not hide main window. Attempting to close all and only open taskbar."))
            self.log.debug(_excp, exc_info=1)
            if force:
                try:
                    self.main.remove_on_close = True
                    self.main.close()
                    self.main = None
                    self.main = self.create_main_window()
                except Exception as _excp:
                    self.log.error(QtCore.QCoreApplication.translate("logs", "Could not force main window restart."))
                    self.log.debug(_excp, exc_info=1)
                    raise
            elif errors == "strict":
                raise
            else:
                return False
        else:
            return True
        #force hide settings
        try:
            #if open close
            if self.main:
                self.close_main_window()
            #re-open
            self.main = MainWindow()
            self.main.app_message.connect(self.process_message)
        except:
            self.log.error(QtCore.QCoreApplication.translate("logs", "Could close and re-open the main window."))
            self.log.debug(_excp, exc_info=1)
            if errors == "strict":
                raise
            else:
                return False
        else:
            return True
        return False

    def close_main_window(self, force_close=None):
        """
        Closes the main window and task-bar. Only removes the GUI components without closing the application.

        @param force_close bool If the application fails to kill the main window, the whole application should be shut down.
        @return bool 
        """
        try:
            self.main.remove_on_close = True
            self.main.close()
            self.main = False
        except Exception as _excp:
            self.log.error(QtCore.QCoreApplication.translate("logs", "Could not close main window."))
            if force_close:
                self.log.info(QtCore.QCoreApplication.translate("logs", "force_close activated. Closing application."))
                try:
                    self.main.deleteLater()
                    self.main.exitEvent()
                except:
                    self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not close main window using its internal mechanisms. Application will be halted."))
                    self.log.debug(_excp, exc_info=1)
                    sys.exit(1)
            else:
                self.log.error(QtCore.QCoreApplication.translate("logs", "Could not close main window."))
                self.log.info(QtCore.QCoreApplication.translate("logs", "It is reccomended that you close the entire application."))
                self.log.debug(_excp, exc_info=1)
                raise
                

    def create_controller(self):
        """
        Creates a controller to act as the middleware between the GUI and the commotion core.
        """
        try:
            pass #replace when controller is ready
            #self.controller = CommotionController() #TODO Implement controller
            #self.controller.init() #??????
        except Exception as _excp:
            self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not create controller. Application must be halted."))
            self.log.debug(_excp, exc_info=1)
            raise

    def close_controller(self, force_close=None):
        """
        Closes the controller process.

        @param force_close bool If the application fails to kill the controller, the whole application should be shut down.
        """
        try:
            pass #TODO Swap with below when controller close function is instantiated
            #if self.controller.close():
            #    self.controller = None
        except Exception as _excp:
            self.log.error(QtCore.QCoreApplication.translate("logs", "Could not close controller."))
            if force_close:
                self.log.info(QtCore.QCoreApplication.translate("logs", "force_close activated. Closing application."))
                try:
                    del self.controller
                except:
                    self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not close main window using its internal mechanisms. Application will be halted."))
                    self.log.debug(_excp, exc_info=1)
                    sys.exit(1)
            else:
                self.log.error(QtCore.QCoreApplication.translate("logs", "Could not cleanly close controller."))
                self.log.info(QtCore.QCoreApplication.translate("logs", "It is reccomended that you close the entire application."))
                self.log.debug(_excp, exc_info=1)
                raise
    
    def start_full(self):
        """
        Start or switch client over to full client.
        """
        if self.main == False:
            try:
                self.main = MainWindow()
                self.main.app_message.connect(self.process_message)
            except Exception as _excp:
                self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not create Main Window. Application must be halted."))
                self.log.debug(_excp, exc_info=1)
                sys.exit(1)
            else:
                self.main.show()

    def start_daemon(self):
        """
        Start or switch client over to daemon mode. Daemon mode runs the taskbar without showing the main window.
        """
        try:
            #Close main window without closing taskbar
            if self.main:
                self.hide_main_window(force=True, errors="strict")
        except Exception as _excp:
            self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not close down existing GUI componenets to switch to daemon mode."))
            self.log.debug(_excp, exc_info=1)
            raise
        try:
            #create main window and controller
            self.main = self.create_main_window()
            self.main.app_message.connect(self.process_message)
            #if not self.controller: #TODO Actually create a stub controller file
            #    self.controller = create_controller()
        except Exception as _excp:
            self.log.critical(QtCore.QCoreApplication.translate("logs", "Could not start daemon. Application must be halted."))
            self.log.debug(_excp, exc_info=1)
            raise

    def process_message(self, message):
        """
        Process which processes messages an app receives and takes actions on valid requests.
        """
        if message == "showMain":
            if self.main != False:
                self.main.show()
                self.main.raise_()
        elif message == "restart":
            self.log.info(self.translate("logs", "Received a message to restart. Restarting Now."))
            self.restart_client(force_close=True) #TODO, might not want strict here post-development
        else:
            self.log.info(self.translate("logs", "message \"{0}\" not a supported type.".format(message)))

    def crash(self, message):
        #TODO Properly handle crash here.
        print(message)
        self.exit(1)
        

if __name__ == "__main__":
    main()
