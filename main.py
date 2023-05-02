from PyQt5 import QtWidgets, uic
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QInputDialog, QLineEdit, QFileDialog
import mainwindow
import os
from threading import *
import src.start as start
thisdir = os.getcwd()
homedir = os.path.expanduser(r"~")

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui = mainwindow.Ui_MainWindow()
        self.ui.setupUi(self)

        #Define Variables
        self.input_file = ''
        self.output_folder = ''
        self.output_folder = f'{homedir}'

        self.pin_functions()
        self.show()

    def pin_functions(self):

        self.ui.Input_video_rife.clicked.connect(self.openFileNameDialog)
        self.ui.Output_folder_rife.clicked.connect(self.openFolderDialog)
        self.ui.Rife_Model.setCurrentIndex(5)
        
        self.ui.RifeStart.clicked.connect(lambda: Thread(target=lambda: start.start_rife((self.ui.Rife_Model.currentText().lower()),2,self.input_file,self.output_folder)).start())

    def openFileNameDialog(self):

        self.input_file = QFileDialog.getOpenFileName(self, 'Open File', f'{homedir}',"Video files (*.mp4);;All files (*.*)")[0]
    def openFolderDialog(self):
        
        self.output_folder = QFileDialog.getExistingDirectory(self, 'Open Folder')

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
