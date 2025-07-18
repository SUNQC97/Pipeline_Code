from ctypes import *
from enum import Enum
import os
import time
from threading import *
import threading
import inspect  # Angabe der Zeilennumern

from dotenv import load_dotenv

dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
load_dotenv(dotenv_path)



# Arbeitsablauf fuer die Verbindung zu Virtuos
# 1.  !! Init DLL
# 2.  Starte Virtuos
# 3.  !! Festlegen der CORBA Informationen fuer den Server
# 4.  !! Starte die Verbindung mit dem CORBA-Server
# 5.  Lade Virtuos-Projekt
# 6.  Ramp up the project
# 7.  Run self.virtuos
# 8.  !! Starte das zyklische Update und das Update des current set
# 9.  Lese einen Port
#     Schreibe einen Port
#     Aendere einen Parameter
#     Aendere eine Eigenschaft eines Blockbausteins
# 10. !! Stoppe das zyklische Update und das Update des current set
# 11. Stoppe die Simulation
# 12. Ramp down the project
# 13. Schliesse das Projekt in Virtuos
# 11. !! Detach DLL
# !! notwendige Schritte, andere Schritte koennen evtl. uebersprungen werden
# Pfade in Virtuos werden als Strin in hierarchischer Punktnotation uebergeben
# Bsp. "[Hauptblock].[Unterblock].[Port]"
# Die Funktionen geben in der Regel den Status (Erfolg = 0, Misserfolg = -1) zurueck.


class ValueID(Structure):
    """
    Komplexer Datentyp, der die notwendigen Infos enthaelt, um auf die IO-Ports der Simulationsbloecke
    zuzugreifen
    """
    _fields_ = [('valueID', c_int32),
                ('interfaceID', c_int32),
                ('interfaceID2', c_int32),
                ('valueDataType', c_int32),
                ('valueIOType', c_uint32)]
                
    def __init__(self):
        self.valueID = -1
        self.interfaceID = -1
        self.interfaceID2 = -1
        self.valueDataType = -1
        self.valueIOType = 0


class VIODataType(Enum):
    # Datentypen fuer Virtuos
    V_IO_TYPE_UNKNOWN   = 0x0000
    V_IO_TYPE_BOOLEAN   = 0x0001
    V_IO_TYPE_REAL32    = 0x0002
    V_IO_TYPE_REAL64    = 0x0004
    V_IO_TYPE_STRING    = 0x0008
    V_IO_TYPE_INT8      = 0x0010
    V_IO_TYPE_INT16     = 0x0020
    V_IO_TYPE_INT32     = 0x0040
    V_IO_TYPE_INT64     = 0x0080
    V_IO_TYPE_UINT8     = 0x0100
    V_IO_TYPE_UINT16    = 0x0200
    V_IO_TYPE_UINT32    = 0x0400
    V_IO_TYPE_UINT64    = 0x0800
    V_IO_TYPE_WSTRING   = 0x2000
    V_IO_TYPE_UUID      = 0x4000
    V_IO_TYPE_EVENT     = 0x8000
    V_IO_TYPE_C_POINTER = 0x20000


class VIOAccessType(Enum):
    V_IO_ACCESS_READ = 0x0001
    V_IO_ACCESS_WRITE = 0x0002


class ForceType(Enum):
    V_NONE = 0
    V_FORCE = 1  # ! Used to enable forcing of a value in ICommunication::setForced.
    V_RELEASE = 2  # ! Used to disable forcing of a value in ICommunication::setForced.
    V_WRITE_FORCED = 3  # ! Used in the write-Methods of ICommunication to indicate that the value should be written
    # to the "forced" value of a solver variable is disabled.
    V_WRITE_UNFORCED = 4  # ! Used in the write-Methods of ICommunication to indicate that the value should be written
    # to the "unforced" value of a solver variable.


class StatusException(Exception):
    """Raise when status = V_DAMGD"""

    def __init__(self, *args):
        self.message = "A status error was raised. Eine Funktion von VirtuosZugriff konnte nicht ausgefuehrt werden."


# aktuelle Zeilennumer ausgeben
def lineno():
    return inspect.currentframe().f_back.f_lineno


class VirtuosZugriff:
    def __init__(self):
        # lokale Variablen
        self.status = None
        self.ipCorba = None
        self.portCorba = None
        self.serverNameCorba = None
        self.parameterValueID = None
        self.nwd = None
        self.oldDirectory = os.getcwd()
        self.libDll = os.getenv('envLibDll')
        # self.pathVirtuosM = "C:\\Virtuos\\Virtuos_V_2_3_x64\\bin_x64\\VirtuosM_x64.exe"
        # self.pathVirtuosV = "C:\\Virtuos\\Virtuos_V_2_3_x64\\bin_x64\\VirtuosV_x64.exe"
        self.projectVirtuos = None
        self.pathToSave = None  # Speicherort des Virtuos-Projekts
        self.prozessIDV = c_int64()  # ProzessID von VirtuosV
        self.prozessIDM = c_int64()  # ProzessID von VirtuosM
        self.leseparameter = None
        self.schreibparameter = None  # zu schreibende Parameter
        self.maxBufferLen = None
        self.remainingSets = None
        self.bufferFillState = None
        self.continueUpdate = 0  # Endkriterium fuer Update des CurrentSet
        # Schloss zum vollständigen Durchführen einer Funktion ohne Unterbrechung
        self.lock = threading.RLock()
        self.vi = None  # Verbindung zur Virtuos-DLL

    ## Definition allgemeiner Variablen
    V_SUCCD = 0
    V_DAMGD = -1
    V_REPEAT = 1
    V_CORBA_INTERFACE_CHANGED_RAMPUP = 2007
    V_CORBA_INTERFACE_CHANGED_RAMPDOWN = 2010
    V_CORBA_INTERFACE_CHANGED_DATA_RESET = 2013
    V_CORBA_INTERFACE_CHANGED_INITIALIZED = 2016

    ## Definition von allgemeinen Funktionen
    def stringToCharP(self, string):  # Umwandlung von string zu c_char_p
        """
        Converts a string to a C-compatible char pointer.

        Args:
            string (str): The string to be converted.

        Returns:
            c_char_p: A C-compatible char pointer representing the UTF-8 encoded string.
        """
        y = c_char_p(string.encode("utf-8"))
        return y
    
    def stringListToCharP(self, List):
        """
        Converts a list of strings to a list of C-compatible char pointers.

        Args:
            List (list): The list of strings to be converted.

        Returns:
            list: A list of C-compatible char pointers representing the UTF-8 encoded strings.
        """
        charList=[]
        for string in List:
            char = c_char_p(string.encode("utf-8"))
            charList.append(char)
        return charList
    
    def strToByte(self, string):  # Umwandlung von string zu byte
        """
        Converts a string to a bytes object representing the UTF-8 encoded string.

        Args:
            string (str): The string to be converted.

        Returns:
            bytes: A bytes object representing the UTF-8 encoded string.
        """
        y = string.encode("utf-8")
        return y

    ### Virtuos-Funktionen
    ## Virtuos-Schnittstelle
    # initDLL
    def virtuosDLL(
        self,
        nwd = os.getenv('envNwd'),
        libDll = os.getenv('envLibDll'),
    ):
        # global self.vi
        self.nwd = nwd
        self.libDll = libDll
        self.oldDirectory = os.getcwd()
        # os.chdir(self.nwd)  # Aenderung des work directory, damit dort ausgefuehrt wird, wo die DLL liegt
        # mydll = cdll.LoadLibrary(self.libDll)
        # evtl Abhaengigkeiten von anderen DLLs, die nicht gefunden werden
        self.vi = cdll.LoadLibrary(self.libDll)  # .virtuos_interface_x64
        self.vi.initDLL()
        # self.vi = cdll.virtuos_interface_x64
        # cdll.virtuos_interface_x64.initDLL()

    
    
    # set CORBA-information
    def corbaInfo(
        self, ipCorba="127.0.0.1", portCorba="54322", serverNameCorba="Visualization"
    ):
        """
        Sets the CORBA information for the Virtuos environment.

        Args:
            ipCorba (str): The IP address of the CORBA server. Defaults to "127.0.0.1".
            portCorba (str): The port number of the CORBA server. Defaults to "54322".
            serverNameCorba (str): The name of the CORBA server. Defaults to "Visualization".

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        self.ipCorba = ipCorba
        self.ipCorba = c_char_p(self.ipCorba.encode("utf-8"))
        self.portCorba = portCorba
        self.portCorba = self.stringToCharP(self.portCorba)
        self.serverNameCorba = serverNameCorba
        self.serverNameCorba = self.stringToCharP(self.serverNameCorba)
        if (
            cdll.LoadLibrary(self.libDll).setCorbaInfo(
                self.ipCorba, self.portCorba, self.serverNameCorba
            )
            == 0
        ):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    # start Virtuos
    def startVirtuosExe(self, pathVirtuos= os.getenv('envPathVirtuosExe')):
        """
        Starts the Virtuos executable with the specified path and establishes a connection with the CORBA server.

        Sets the path to the Virtuos executable and initializes the connection to the CORBA server by passing the 
        appropriate parameter. The function returns a status indicating the success or failure of the operation.

        Args:
            pathVirtuos (str): The path to the Virtuos executable. Defaults to the environment variable 'envPathVirtuosExe'.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        self.pathVirtuos = pathVirtuos
        # gleichzeitiger Verbindungsaufbau mit CORBA-Server
        virtuosparameter = "-startcorbaserver"
        virtuosparameter = (c_char_p * 1)(virtuosparameter.encode("utf-8"))
        if (self.vi.startVirtuos(self.stringToCharP(self.pathVirtuos), c_int32(1), virtuosparameter,
                                  pointer(self.prozessIDM)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    def interpretJSFileFn(self, pathJSFile):
        """
        Interprets a JavaScript file with the given path using the Virtuos interface.

        This function sets the path to the JavaScript file to be interpreted and calls the
        Virtuos interface to interpret the file. It updates the status based on the success
        or failure of the operation.

        Args:
            pathJSFile (str): The path to the JavaScript file to be interpreted.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or 
            VirtuosZugriff.V_DAMGD for failure.
        """
        self.pathJSFile = pathJSFile
        
        #jsFile = (c_char_p * 1)(jsFile.encode("utf-8"))
        if (self.vi.interpretJSFile(self.stringToCharP(self.pathJSFile)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    def interpretJSCodeFn(self, jsCode):
        """
        Interprets a JavaScript code snippet using the Virtuos interface.
        """
        self.jsCode = jsCode
        
        #jsCode = (c_char_p * 1)(jsCode.encode("utf-8"))
        if (self.vi.interpretJSCode(self.stringToCharP(self.jsCode)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    def importTSP36(self, pathJSFile):
        self.pathJSFile = pathJSFile

        if (self.vi.importTSP36(self.stringToCharP(self.pathJSFile)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
        
    # Corba-Verbindung aufbauen
    def startConnectionCorba(self):
        """
        Establishes a connection to the CORBA server using the Virtuos interface.

        Calls the Virtuos interface to establish a connection to the CORBA server. The function returns a status 
        indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.startConnection() == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Verbindung ueberpruefen
    def isConnected(self):
        """
        Checks if the connection to Virtuos is established.

        Calls the Virtuos interface to check if the connection to Virtuos is established. The function returns a status
        indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.connected() == 0):
            return VirtuosZugriff.V_SUCCD
        else:
            return VirtuosZugriff.V_DAMGD

    # DLL trennen
    def unloadDLL(self):
        """
        Unloads the Virtuos interface DLL.

        Calls the Virtuos interface to unload the Virtuos interface DLL. The function
        returns a status indicating the success or failure of the operation.

        Returns:
            None
        """

        try:
            self.vi.detachDLL()
        except Exception as e:
            print(e)
            raise Exception("Error at function call self.vi.detachDLL()")
            pass
    
    # Shut down Virtuos
    def stopVirtuosPrgm(self):
        """
        Stops the Virtuos process.

        Calls the Virtuos interface to stop the Virtuos process. The function returns a status
        indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.stopVirtuos() == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # Beenden des Prozesses
    def stopProcess(self, prozessID):
        """
        Stops the Virtuos process gracefully.

        Calls the Virtuos interface to stop the Virtuos process gracefully. The function
        returns a status indicating the success or failure of the operation.

        Args:
            prozessID (int): The process ID of the Virtuos process to stop.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.terminateProcess(prozessID) == 0):
            return VirtuosZugriff.V_SUCCD
        else:
            return VirtuosZugriff.V_DAMGD

    # Hartes Beenden des Prozesses
    def killProcess(self, prozessID):
        """
        Forcefully terminates the Virtuos process.

        Calls the Virtuos interface to forcefully kill the specified Virtuos process. The function
        returns a status indicating the success or failure of the operation.

        Args:
            prozessID (int): The process ID of the Virtuos process to kill.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.killProcess(prozessID) == 0):
            return VirtuosZugriff.V_SUCCD
        else:
            return VirtuosZugriff.V_DAMGD

    # Zustand des Prozesses
    def stateProcess(self, prozessIDM):
        """
        Retrieves the state of the Virtuos process.

        Calls the Virtuos interface to query the state of the Virtuos process
        with the specified process ID. The function returns a status indicating
        the success or failure of the operation, and the actual state of the
        process.

        Args:
            prozessIDM (int): The process ID of the Virtuos process to query.

        Returns:
            tuple: A tuple containing the status of the operation, and the state
            of the Virtuos process. The status is either VirtuosZugriff.V_SUCCD
            for success or VirtuosZugriff.V_DAMGD for failure. The state of the
            process is given as a c_long value.
        """
        prozesszustand = c_long()
        if (self.vi.processState(prozessIDM, pointer(prozesszustand)) == 0):
            return VirtuosZugriff.V_SUCCD, prozesszustand
        else:
            return VirtuosZugriff.V_DAMGD, prozesszustand

    ## Projekt-Schnittstelle
    
    # Projekt in Virtuos laden
    def getProject(self, projectVirtuos, convert=1):
        """
        Loads a Virtuos project from a file.

        This function sets the name of the Virtuos project to be loaded and calls the
        Virtuos interface to load the project. The function returns a status indicating
        the success or failure of the operation.

        Args:
            projectVirtuos (str): The name of the Virtuos project to be loaded.
            convert (int): An optional parameter specifying whether to convert the
            project. Defaults to 1.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or
            VirtuosZugriff.V_DAMGD for failure.
        """

        self.projectVirtuos = projectVirtuos
        dconvert = convert
        if (self.vi.loadProject(self.stringToCharP(self.projectVirtuos), dconvert) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # Ueberpruefen, ob ein Projekt in VirtuosM geoeffnet ist
    def isOpen(self):
        """
        Checks if a Virtuos project is currently open.

        This function checks if a Virtuos project is currently open. The function
        returns a status indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or
            VirtuosZugriff.V_DAMGD for failure.
        """

        if (self.vi.isOpened() == 0):
            return VirtuosZugriff.V_SUCCD
        else:
            return VirtuosZugriff.V_DAMGD

    # Projekt in Virtuos schliessen
    def closeProject(self):
        """
        Closes the currently open Virtuos project.

        This function closes the currently open Virtuos project. The function
        returns a status indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or
            VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.closeProject() == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    def stopConnect(self):
        """
        Stops the connection to Virtuos.

        Calls the Virtuos interface to stop the connection. The function
        returns a status indicating the success or failure of the operation.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or
            VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.stopConnection() == 0):
            VirtuosZugriff.V_SUCCD
        else:
            VirtuosZugriff.V_DAMGD
        return self.status
            
    # !test Activates the 'Assisted TwinCAT Project Management' of a configuration.  Also sets the configuration as active configuration
    def activateAssistedTwinCProjectMgmt(self, configName):
        """
        Activates the 'Assisted TwinCAT Project Management' of a configuration.  Also sets the configuration as active configuration

        Args:
            configName (str): Name of the configuration to be activated

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure
        """
        self.configName = configName
        if (
            self.vi.activateAssistedTwinCATProjectManagement(self.stringToCharP(self.configName)) == 0
        ):  # 0 = VirtuosZugriff.V_SUCCD
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
            
    # !test import twinCAT project ( i_filePath - Full path to the *.tszip)
    def importTwinCProject(self, configName, targetName, filePath):
        """
        Imports a TwinCAT project into Virtuos

        Args:
            configName (str): Name of the configuration to be imported
            targetName (str): Name of the target to be imported
            filePath (str): Full path to the *.tszip file to be imported

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure
        """
        self.configName = configName
        self.targetName = targetName
        self.filePath = filePath
        if (
            self.vi.importTwinCATProject(
                self.stringToCharP(self.configName), self.stringToCharP(self.targetName), self.stringToCharP(self.filePath)
            )
            == 0
        ):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # set exclude from execution
    def setExclFromExecution(self, hierarchicalModelName, bExclude):
        
        """
        Sets the exclude from execution flag for a given hierarchical model name.

        Args:
            hierarchicalModelName (str): The hierarchical model name to be set.
            bExclude (bool): Whether to exclude the model from execution.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure
        """
        self.hierarchicalModelName = hierarchicalModelName
        self.bExclude = bExclude
        if(self.vi.setExcludeFromExecution(self.stringToCharP(self.hierarchicalModelName), self.bExclude) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # !test getEntityComment from hierarchicalModelName
    # i_entityType can be "model", "input", "output"
    def getEntityCom(self, hierarchicalModelName, comment, sizeOfComment, entityType):
        """
        Retrieves the comment associated with a specified entity in the hierarchical model.

        Args:
            hierarchicalModelName (str): The name of the hierarchical model.
            comment (str): A placeholder for the comment to be retrieved.
            sizeOfComment (int): The size of the comment buffer.
            entityType (str): The type of entity, which can be "model", "input", or "output".

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or 
            VirtuosZugriff.V_DAMGD for failure.
        """
        self.hierarchicalModelName = hierarchicalModelName
        self.comment = comment
        self.sizeOfComment = sizeOfComment
        self.entityType = entityType
        if(self.vi.getEntityComment(self.stringToCharP(self.hierarchicalModelName), self.stringToCharP(self.comment), self.sizeOfComment ,self.stringToCharP(self.entityType)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # !test change EntityComment from hierarchicalModelName
    # i_entityType can be "model", "input", "output"
    def changeEntityCom(self, hierarchicalModelName, comment, entityType):
        """
        Changes the comment associated with a specified entity in the hierarchical model.

        Args:
            hierarchicalModelName (str): The name of the hierarchical model.
            comment (str): The new comment to be associated with the entity.
            entityType (str): The type of entity, which can be "model", "input", or "output".

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """

        self.hierarchicalModelName = hierarchicalModelName
        self.comment = comment
        self.entityType = entityType
        if(self.vi.changeEntityComment(self.stringToCharP(self.hierarchicalModelName), self.stringToCharP(self.comment), self.stringToCharP(self.entityType)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        
    # Projekt in Virtuos speichern
    def saveVirtuosAs(self, pathToSave):
        """
        Saves the current Virtuos project to the specified path.

        This function sets the path where the Virtuos project should be saved
        and calls the Virtuos interface to perform the save operation. It updates 
        the status based on the success or failure of the operation.

        Args:
            pathToSave (str): The path where the Virtuos project should be saved.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success 
            or VirtuosZugriff.V_DAMGD for failure.
        """
        self.pathToSave = pathToSave
        if (self.vi.saveProjectAs(self.stringToCharP(self.pathToSave)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Merge Projekt
    def mergeProject(self, pathToEcf, assemblyName):
        """
        Merges the Virtuos project with the specified .ecf file.

        This function sets the path to the .ecf file and the name of the assembly
        and calls the Virtuos interface to perform the merge operation. It updates
        the status based on the success or failure of the operation.

        Args:
            pathToEcf (str): The path to the .ecf file.
            assemblyName (str): The name of the assembly.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        if (self.vi.merge(self.stringToCharP(pathToEcf), self.stringToCharP(assemblyName)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # VIRTUOSREMOTEINTERFACE_API VRESULT setSimulationManagerConfiguration(const V_CHAR8 *i_simulationManagerConfigurationName);
    def setSimManagerConfig(self, i_simulationManagerConfigurationName):
        """
        Sets the configuration of the simulation manager to the specified name.

        This function sets the name of the simulation manager configuration and
        calls the Virtuos interface to perform the configuration change. It updates
        the status based on the success or failure of the operation.

        Args:
            i_simulationManagerConfigurationName (str): The name of the configuration to be set.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success or VirtuosZugriff.V_DAMGD for failure.
        """
        self.i_simulationManagerConfigurationName = i_simulationManagerConfigurationName
        if (self.vi.setSimulationManagerConfiguration(self.stringToCharP(self.i_simulationManagerConfigurationName)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # VIRTUOSREMOTEINTERFACE_API VRESULT getSimulationManagerConfiguration(V_CHAR8 *o_simulationManagerConfigurationName, V_UINT32 *io_size);
    #! test   
    def getSimManagerConfig(self):
        
        """
        Retrieves the name of the currently active simulation manager configuration.

        This function sets the string size to the maximum length of the two possible
        configuration names and calls the Virtuos interface to perform the retrieval.
        It updates the status based on the success or failure of the operation.

        Returns:
            tuple: A tuple containing the status of the operation (int), the name of the
            configuration (str), and the size of the string (int).
        """
        stringSize = (max(len("Configuration 1 (Windows)"), len("Configuration 2 (TwinCAT)")) + 1)
        stringSize_c_type = c_uint32(stringSize)
        simConfig = (c_char * stringSize)()
        if (self.vi.getSimulationManagerConfiguration(simConfig, pointer(stringSize_c_type)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        simConfig = (simConfig.value).decode("utf-8")
        stringSize = stringSize_c_type.value
        return self.status, simConfig, stringSize
    
    # VIRTUOSREMOTEINTERFACE_API VRESULT getSimulationManagerConfigurationNames(V_UINT32 *io_numberOfConfigurations, V_UINT32 i_maxStringLength, V_CHAR8* o_simulationConfigurationNames[]);
    #! test
    def getSimManagerConfigNames(self, io_numberOfConfigurations, i_maxStringLength, o_simulationConfigurationNames):
        """
        Retrieves the names of available simulation manager configurations.

        This function calls the Virtuos interface to obtain the list of configuration
        names for the simulation manager. It updates the status based on the success
        or failure of the operation.

        Args:
            io_numberOfConfigurations (int): A pointer to the number of configurations
                                            to be retrieved. This value is updated
                                            with the actual number of configurations.
            i_maxStringLength (int): The maximum length of each configuration name string.
            o_simulationConfigurationNames (list of str): A list to store the retrieved
                                                        configuration names.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success
                or VirtuosZugriff.V_DAMGD for failure.
        """
        self.io_numberOfConfigurations = io_numberOfConfigurations
        self.i_maxStringLength = i_maxStringLength
        self.o_simulationConfigurationNames = o_simulationConfigurationNames
        if (self.vi.getSimulationManagerConfigurationNames(self.io_numberOfConfigurations, self.i_maxStringLength, self.stringListToCharP(self.o_simulationConfigurationNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
            
    # VIRTUOSREMOTEINTERFACE_API VRESULT getSolverNames(const V_CHAR8 *i_simulationManagerConfigurationName, V_UINT32 *io_numberOfSolvers, V_UINT32 i_maxStringLength, V_CHAR8* o_solverNames[]);
    #! test
    def getSolverNames(self, i_simulationManagerConfigurationName, io_numberOfSolvers, i_maxStringLength, o_solverNames):
        """
        Retrieves the names of available solvers for a given simulation manager configuration.

        This function calls the Virtuos interface to obtain the list of solver names
        associated with a specified simulation manager configuration. It updates the
        status based on the success or failure of the operation.

        Args:
            i_simulationManagerConfigurationName (str): The name of the simulation manager configuration.
            io_numberOfSolvers (int): A pointer to the number of solvers to be retrieved. This value
                                    is updated with the actual number of solvers.
            i_maxStringLength (int): The maximum length of each solver name string.
            o_solverNames (list of str): A list to store the retrieved solver names.

        Returns:
            int: The status of the operation, either VirtuosZugriff.V_SUCCD for success
                or VirtuosZugriff.V_DAMGD for failure.
        """
        self.i_simulationManagerConfigurationName = i_simulationManagerConfigurationName
        self.io_numberOfSolvers = io_numberOfSolvers
        self.i_maxStringLength = i_maxStringLength
        self.o_solverNames = o_solverNames
        if (self.vi.getSolverNames(self.stringToCharP(self.i_simulationManagerConfigurationName), self.io_numberOfSolvers, self.i_maxStringLength, self.stringListToCharP(self.o_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
            
    ## Simulations-Schnittstelle
    # Ramp Up der Simulation
    def rampUpSim(self):
        if (self.vi.rampUp() == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Ramp Down der Simulation
    def rampDownSim(self):
        if (self.vi.rampDown() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Starten der Simulation
    def startSim(self):
        if (self.vi.run() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Beenden der Simulation
    def stopSim(self):
        if (self.vi.stop() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # VIRTUOSREMOTEINTERFACE_API VRESULT rampUp2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def rampUpV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames
        
        if (self.vi.rampUp2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # VIRTUOSREMOTEINTERFACE_API VRESULT rampDown2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def rampDownV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames
        
        if (self.vi.rampDown2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    #  VIRTUOSREMOTEINTERFACE_API VRESULT reset2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def rampUpV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames
        
        if (self.vi.reset2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # VIRTUOSREMOTEINTERFACE_API VRESULT run2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def runV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames
        
        if (self.vi.run2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    # VIRTUOSREMOTEINTERFACE_API VRESULT stop2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def stopV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames
        
        if (self.vi.stop2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status
    
    #  VIRTUOSREMOTEINTERFACE_API VRESULT step2(V_INT32 i_noOfSolvers, V_CHAR8* i_solverNames[]);
    # !test
    def stepV2(self, i_noOfSolvers, i_solverNames):
        self.i_noOfSolvers = i_noOfSolvers
        self.i_solverNames = i_solverNames

        if (self.vi.step2(self.i_noOfSolvers, self.stringListToCharP(self.i_solverNames)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
            
    # Ein Schritt der Simulation
    def simStep(self):
        if (self.vi.step() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
            print("Step Failed")
        return self.status

    # Reset der Simulation
    def simReset(self):
        if (self.vi.reset() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Abfrage des Simulationszustands
    def simStatus(self):
        groesse = (
            max(len("Suspended"), len("Ready"), len("Running")) + 1
        )  # + 1 fuer Null-Terminator
        groesse_c_type = c_uint32(groesse)
        simZustand = (c_char * groesse)()
        if (
            self.vi.getSimulationStatus(simZustand, pointer(groesse_c_type))
            == VirtuosZugriff.V_SUCCD
        ):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        simZustand = (simZustand.value).decode("utf-8")
        groesse = groesse_c_type.value
        return self.status, simZustand, groesse

    ## Modell-Schnittstelle
    # Eigenschaft eines Projektbaustein aendern
    def setPropertyBlock(self, pathBlock, propertyValue):
        # Es koennen nur Eigenschaften geaendert werden, die als property in einem Bustein vorhanden sind
        self.pathBlock = pathBlock
        self.propertyValue = propertyValue
        if (self.vi.setProperty(self.stringToCharP(self.pathBlock), self.stringToCharP(self.propertyValue)) == 0):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Parameter eines Projektbausteins lesen
    def getParameterBlock(self, parameterName, parameterValue):
        
        stringSize = (
            max(len("1"), len("0"))
        )  # relay an oder aus
        stringSize_c_type = c_uint32(stringSize)
        dparameterName = self.stringToCharP(parameterName)  # Parametername in hierachischer Punktnotation
        dparameterValue = self.stringToCharP(parameterValue)  # Wert als String uebergeben
        # Groesse des Strings
        if (self.vi.getParameter(dparameterName, dparameterValue, pointer(stringSize_c_type)) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status


    def getParameterBlock_New(self, parameterName):
        buffer_size = 2048
        value_buffer = create_string_buffer(buffer_size)
        size_c_type = c_uint32(buffer_size)

        dparameterName = self.stringToCharP(parameterName)

        status = self.vi.getParameter(dparameterName, value_buffer, pointer(size_c_type))

        if status == VirtuosZugriff.V_SUCCD:
            self.status = status
            return value_buffer.value.decode("utf-8")  # 返回实际值
        else:
            self.status = VirtuosZugriff.V_DAMGD
            return None


    
    # Parameter eines Projektbausteins aendern
    def setParameterBlock(self, parameterName, parameterValue):
        dparameterName = self.stringToCharP(parameterName)  # Parametername in hierachischer Punktnotation
        dparameterValue = self.stringToCharP(parameterValue)  # Wert als String uebergeben
        if (self.vi.setParameter(dparameterName, dparameterValue) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    ## Kommunikations-Schnittstelle
    # ValueID der Parameter, Rueckgabe: status und ValueID
    def readValueID(self, parameterPfad, dataType=None):
        # evtl. Umwandlung in Liste
        if not isinstance(parameterPfad, list) and not isinstance(parameterPfad, tuple):
            parameterPfad = [parameterPfad]
        # Umwandlung des Parameterpfads in Ctypes
        dparameterPfad = (c_char_p * len(parameterPfad))()
        for i in range(0, len(dparameterPfad)):
            dparameterPfad[i] = self.strToByte(parameterPfad[i])
        self.parameterValueID = (ValueID * len(dparameterPfad))()
        # Default datentyp ist REAL64
        if dataType is None:
            ddataType = [VIODataType.V_IO_TYPE_REAL64.value] * len(dparameterPfad)
        elif isinstance(dataType, (list, tuple)):
            ddataType = [dt.value if isinstance(dt, VIODataType) else dt for dt in dataType]
        else:
            ddataType = [dataType.value if isinstance(dataType, VIODataType) else dataType] * len(dparameterPfad)
        self.status = -1
        # Iteration ueber alle Parameter
        for ipara in range(0, len(dparameterPfad)):
            # Es werden alle ValueIDs mit lesendem Zugriff bestimmt: ACCESS_READ
            # Dies funktioniert auch bei verbundenen Ports.
            # Die ValueIDs koennen trotzdem zum Schreiben benutzt werden.
            if (self.vi.getValueID(dparameterPfad[ipara], ddataType[ipara], VIOAccessType.V_IO_ACCESS_READ.value,
                                   pointer(self.parameterValueID[ipara])) == VirtuosZugriff.V_SUCCD):
                nr = ipara + 1
                self.status = VirtuosZugriff.V_SUCCD

                print('Getting Value ID for variable ' + str(dparameterPfad[ipara]) + 'succeeded');
                print(self.parameterValueID[ipara])
            else:
                self.status = VirtuosZugriff.V_DAMGD
                print('Getting Value ID for variable ' + str(dparameterPfad[ipara]) + 'failed');
                print(self.parameterValueID[ipara])
                # Die ValueID wird als Structure zurueck gegeben
        return self.status, self.parameterValueID

    # Parameter lesen, Rueckgabe: status und Parameterwert
    def readValue(self, parameterValueID, dataType=None):
        with self.lock:
            # Kopie, wenn ein mutuable vorliegt
            try:
                dparameterValueID = parameterValueID.copy()
            except AttributeError:
                dparameterValueID = parameterValueID
            # Umwandlung in Liste, wenn noch nicht vorhanden
            try:
                a = dparameterValueID[0]
            except TypeError:
                dparameterValueID = (ValueID * 1)()
                dparameterValueID[0] = parameterValueID.copy()
            except:
                pass
            leseparameter = [None] * len(dparameterValueID)
            # Default Datentyp ist REAL64
            if dataType is None:
                ddataType = [VIODataType.V_IO_TYPE_REAL64] * len(dparameterValueID)
            elif isinstance(dataType, (list, tuple)):
                ddataType = dataType.copy()
            else:
                ddataType = [dataType] * len(dparameterValueID)

            nr = 0
            ivalueID = -1
            # Schleife ueber alle ValueIDs
            for valueID in dparameterValueID:
                ivalueID += 1
                nr += 1
                try:
                    # Lesen der unterschiedlichen Datentypen
                    if (ddataType[ivalueID] == VIODataType.V_IO_TYPE_REAL64):
                        dleseparametera = c_double(0)
                        if (self.vi.readReal64Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_BOOLEAN):
                        dleseparametera = c_bool(0)
                        if (self.vi.readBooleanValue(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_REAL32):
                        dleseparametera = c_double(0)
                        if (self.vi.readReal32Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_UINT8):
                        dleseparametera = c_uint(0)
                        if (self.vi.readUInt8Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_INT8):
                        dleseparametera = c_int(0)
                        if (self.vi.readInt8Value(dparameterValueID[ivalueID],
                                                  pointer(dleseparametera)) == VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_UINT16):
                        dleseparametera = c_uint(0)
                        if (self.vi.readUInt16Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_INT16):
                        dleseparametera = c_int(0)
                        if (self.vi.readInt16Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_UINT32):
                        dleseparametera = c_uint(0)
                        if (self.vi.readUInt32Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_INT32):
                        dleseparametera = c_int(0)
                        if (self.vi.readInt32Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_UINT64):
                        dleseparametera = c_uint(0)
                        if (self.vi.readUInt64Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_INT64):
                        dleseparametera = c_int(0)
                        if (self.vi.readInt64Value(dparameterValueID[ivalueID], pointer(dleseparametera)) ==
                                VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD
                    elif (ddataType[ivalueID] == VIODataType.V_IO_TYPE_STRING):
                        dleseparametera = c_char(0)
                        self.maxBufferLen = (c_uint * len(dparameterValueID))(100)
                        dmaxBufferLena = c_uint(0)
                        if (self.vi.readStringValue(dparameterValueID[ivalueID], pointer(dleseparametera),
                                                    pointer(dmaxBufferLena)) == VirtuosZugriff.V_SUCCD):
                            leseparameter[ivalueID] = dleseparametera
                            self.maxBufferLen[ivalueID] = dmaxBufferLena
                            self.status = VirtuosZugriff.V_SUCCD
                        else:
                            self.status = VirtuosZugriff.V_DAMGD

                    else:
                        self.status = VirtuosZugriff.V_DAMGD

                except Exception as e:
                    print(e)
                    raise Exception(
                        "Error in function readValue() attempting to vi.Read_*_Value"
                    )
                    pass
        # Umwandlung der ctypes
        for jleseparameter in range(len(leseparameter)):
            if leseparameter[jleseparameter] is not None:
                try:
                    leseparameter[jleseparameter] = leseparameter[jleseparameter].value
                except AttributeError:
                    # 对于不是 ctypes 类型的值（可能是已转好的），跳过
                    pass
            else:
                # Wenn der Parameter nicht gelesen werden konnte, wird None zurueckgegeben  
                 leseparameter[jleseparameter] = None
        return self.status, leseparameter

    # Parameter schreiben
    def writeValue(self, parameterValueID, schreibparameter, dataType=None):
        # Kopie, wenn ein mutuable vorliegt
        try:
            lparameterValueID = parameterValueID.copy()
        except AttributeError:
            lparameterValueID = parameterValueID
        # Umwandlung in Liste, wenn noch nicht vorhanden
        try:
            a = lparameterValueID[0]
        except TypeError:
            lparameterValueID = (ValueID * 1)()
            lparameterValueID[0] = parameterValueID.copy()
        except:
            pass
        # Ports forcen, bevor sie beschrieben werden
        self.status = self.forcePorts(lparameterValueID)
        # Schreibparameter in Liste umwandeln
        if not isinstance(schreibparameter, list):
            self.schreibparameter = [schreibparameter]
        else:
            self.schreibparameter = schreibparameter[:]
        # Default Datentyp ist REAL64
        if dataType is None:
            ddataType = [VIODataType.V_IO_TYPE_REAL64] * len(self.parameterValueID)
        else:
            ddataType = dataType.copy()
        # Iteration ueber alle zu schreibenden Parameter
        for i in range(0, len(self.schreibparameter)):
            nr = i + 1
            # Unterscheidung der Datentypen
            if (ddataType[i] == VIODataType.V_IO_TYPE_REAL64):
                if (self.vi.writeReal64Value(lparameterValueID[i], c_double(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_BOOLEAN):
                if (self.vi.writeBooleanValue(lparameterValueID[i], c_bool(self.schreibparameter[i]),
                                              ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_REAL32):
                if (self.vi.writeReal32Value(lparameterValueID[i], c_double(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_UINT8):
                if (self.vi.writeUInt8Value(lparameterValueID[i], c_uint(self.schreibparameter[i]),
                                            ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_UINT16):
                if (self.vi.writeUInt16Value(lparameterValueID[i], c_uint(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_UINT32):
                if (self.vi.writeUInt32Value(lparameterValueID[i], c_uint(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_UINT64):
                if (self.vi.writeUInt64Value(lparameterValueID[i], c_uint(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_INT8):
                if (self.vi.writeInt8Value(lparameterValueID[i], c_int(self.schreibparameter[i]),
                                           ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_INT16):
                if (self.vi.writeInt16Value(lparameterValueID[i], c_int(self.schreibparameter[i]),
                                            ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_INT32):
                if (self.vi.writeInt32Value(lparameterValueID[i], c_int(self.schreibparameter[i]),
                                            ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_INT64):
                if (self.vi.writeInt64Value(lparameterValueID[i], c_int(self.schreibparameter[i]),
                                            ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            elif (ddataType[i] == VIODataType.V_IO_TYPE_STRING):
                if (self.vi.writeStringValue(lparameterValueID[i], c_char_p(self.schreibparameter[i]),
                                             ForceType.V_WRITE_FORCED.value) == VirtuosZugriff.V_SUCCD):
                    self.status = VirtuosZugriff.V_SUCCD
                else:
                    self.status = VirtuosZugriff.V_DAMGD
            else:
                self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Force Ports
    def forcePorts(self, parameterValueID):
        # Ueberpruefen, ob Array oder List uebergeben ist; ansonsten umwandeln
        # Kopie, falls ein mutuable vorliegt
        try:
            a = parameterValueID[0]
            if isinstance(parameterValueID, tuple):
                dparameterValueID = parameterValueID
            else:
                dparameterValueID = parameterValueID.copy()
        except TypeError:
            dparameterValueID = (ValueID * 1)()
            if isinstance(parameterValueID, tuple):
                dparameterValueID[0] = parameterValueID
            else:
                dparameterValueID[0] = parameterValueID.copy()
        except Exception as e:
            print(e)
            raise Exception("Error at function call forcePorts()")
            pass
        # Iteration ueber alle Parameter
        for i in range(0, len(dparameterValueID)):
            nr = i + 1
            if (self.vi.setForced(dparameterValueID[i], ForceType.V_FORCE.value) == VirtuosZugriff.V_SUCCD):
                self.status = VirtuosZugriff.V_SUCCD
            else:
                self.status = VirtuosZugriff.V_DAMGD
        return self.status

    # Unforce aller Ports
    def unforcePorts(self):
        if (self.vi.unforceAll() == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD
        return self.status

    ## Update
    # Starten des zyklischen Updates, update rate in ms
    def startUpdate(self, updateRate=10):
        # vorhandene Anzahl an Datensets
        self.remainingSets = c_int32(0)
        self.bufferFillState = c_long(0)
        if (self.vi.startCyclicUpdate(updateRate) == VirtuosZugriff.V_SUCCD):
            self.continueUpdate = 1  # Endkriterium fuer das Update des CurrentSet
            time.sleep(0.03)  # wichtig: Pause vor dem ersten Update des CurrentSet ist notwendig
            self.vi.updateCurrentSet(pointer(self.remainingSets), pointer(self.bufferFillState))
            # Thread fuer das kontinuierliche Update des CurrentSet im Hintergrund
            t = Thread(target=self.startUpdateCurrentSet, args=(updateRate,))
            t.start()  # Start des Threads
        else:
            self.continueUpdate = 0

    def startCyclicUpdate(self, updateRate=10):
        self.remainingSets = c_int32(0)
        self.bufferFillState = c_long(0)
        if (self.vi.startCyclicUpdate(updateRate) == VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
            self.continueUpdate = 1
            time.sleep(0.03)  # wichtig: Pause vor dem ersten Update des CurrentSet ist notwendig
        else:
            self.status = VirtuosZugriff.V_DAMGD

    # Starten des zyklischen Updates ohne CurrentSet, update rate in ms
    # CurrentSet muss getrennt gestartet werden
    def startZyklUpdate(self, updateRate=10):
        # vorhandene Anzahl an Datensets
        self.remainingSets = c_int32(0)
        self.bufferFillState = c_long(0)
        if (self.vi.startCyclicUpdate(updateRate) == VirtuosZugriff.V_SUCCD):
            self.continueUpdate = 1
            time.sleep(0.03)  # wichtig: Pause vor dem ersten Update des CurrentSet ist notwendig
        else:
            # Abbruchkriterium fuer CurrenSet, dessen Update nicht ohne zyklisches Update stattfinden kann
            self.continueUpdate = 0

    # Starten des Updates des CurrentSet
    def startUpdateCurrentSet(self, updateRate):
        while (self.continueUpdate == 1):

            # todo: Zugriff mit mutex gegen read/write funktionen verriegeln
            self.status = self.vi.updateCurrentSet(pointer(self.remainingSets), pointer(self.bufferFillState))


            # Update des CurrentSet in aehnlicher Haeufigkeit wie zyklisches Update
            if self.remainingSets.value == 0:
                time.sleep((updateRate / 1000) * 1)
        return self.status

    def singleUpdateCurrentSet(self, sleep_time):
        i = 1
        while (
            self.vi.updateCurrentSet(
                pointer(self.remainingSets), pointer(self.bufferFillState)
            )
            != VirtuosZugriff.V_SUCCD
        ):
            i = i + 1
            time.sleep(sleep_time)
            if i >= 1000:
                return True
            pass
        return False
        # print(i)

    # Stop des zyklischen Updates
    def stopUpdate(self):
        self.status = self.vi.stopCyclicUpdate()
        # Endsignal fuer Update des CurrentSet
        self.continueUpdate = 0
        return self.status, self.continueUpdate
    
    #export IO ProtsByName
    def exportIO(self,SubmodelBlock,pathToSave):
        self.SubmodelBlock = SubmodelBlock
        self.pathToSave = pathToSave
        if(self.vi.exportVirtualIOPortsByName(self.stringToCharP(self.SubmodelBlock), self.stringToCharP(self.pathToSave)) ==  VirtuosZugriff.V_SUCCD):
            self.status = VirtuosZugriff.V_SUCCD
        else:
           self.status = VirtuosZugriff.V_DAMGD 
        return self.status
    
    #export IO Connection
    
    def exportConnectionIO(self,pathToSave):
        self.pathToSave = pathToSave    
        noOfSubmodels = 1
        #self.SubmodelBlockList = SubmodelBlockList
        
        #print(c_char_p(self.SubmodelBlockList[0].encode("utf-8")))
        
        #print(self.stringListToCharP(self.SubmodelBlockList))
    
        #test1 = self.stringListToCharP(SubmodelBlockList)
        #print(test1[:])
        
        if(self.vi.exportVirtualSyncConnections(noOfSubmodels ,self.stringToCharP("[Block Diagram].[Sub1]"), self.stringToCharP(self.pathToSave), True) ==  VirtuosZugriff.V_SUCCD):
             self.status = VirtuosZugriff.V_SUCCD
        else:
            self.status = VirtuosZugriff.V_DAMGD 
        return self.status
"""
Hier nicht definierte Funktionen, die in der DLL enthalten sind:
VRESULT getClientID(char* o_clientID, V_UINT32 *io_size);
VRESULT saveProject();
VRESULT setSolverType(const char *i_solverType);
VRESULT getProjectName(char* o_loadedFileName, V_UINT32 *io_size);
VRESULT readChangedStringValue(const ValueID i_id, char *o_value, V_UINT32 *io_size, V_BOOLEAN *o_changed);
VRESULT setBuffered(V_BOOLEAN i_buffered, V_INT32 i_maxFiFoSize = 10000);
VRESULT index(V_INT32 i_row, V_INT32 i_column, ModelIndex *i_parentIndex, ModelIndex *o_childIndex);
VRESULT rowCount(ModelIndex *i_parentIndex, V_INT32 *o_count);
VRESULT columnCount(ModelIndex *i_parentIndex, V_INT32 *o_count);
VRESULT getData(ModelIndex *i_index, V_INT32 i_role, char* o_data, V_UINT32 *io_size);
VRESULT parent(ModelIndex *i_index, ModelIndex *o_parentIndex)
exportVirtualIOPortsByName(const V_CHAR8* i_hierarchicalModelName, const V_CHAR8* i_filePath);
exportVirtualSyncConnections(noOfSubmodels, hierarchicalNames, "D://temp//virtualConnectionsExport.csv", true);
"""
