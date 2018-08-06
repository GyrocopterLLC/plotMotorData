#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Measure motor paramters live.

TODO:
 -  Separate thread or something to speed up collecting data without causing
    UI freeze.
 -  More than 5 plot lines.
 -  Named plot lines.
 -  Change the selector popup...ability to change number of variables, data rate,
    dynamically show the right number of combobox dropdowns.
"""


from pyqtgraph.Qt import QtGui, QtCore
#from PyQt5.QtWidgets import QWidget, QMessageBox, QApplication
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot
import numpy as np
import pyqtgraph as pg
from pyqtgraph.ptime import time
import serial
from serial.tools import list_ports
import sys
import struct

size_arrays = 5000

class ListenToComThread(QThread):
    # new_data_available = pyqtSignal(np.ndarray)
    
    def __init__(self):
        QThread.__init__(self)
    def __del__(self):
        self.wait()
    
    def setNumPlots(self,numPlots = 10):
        self.data = np.zeros(shape=(numPlots,size_arrays))
        self.numPlots = numPlots
    
    def setSerialPort(self,ser):
        self.ser = ser
        
    def exit_now(self):
        self.exiting = True
        
    ### Run thread debugging version ###
    # def run(self):
        # self.exiting = False
        # print('listening for data...')
        # last_time = time()
        # while not self.exiting:
            # num_data = self.numPlots
            # self.data[:num_data,:-1] = self.data[:num_data,1:]
            # self.data[0,-1] = self.data[0,-2] + 0.001
            # if(self.data[0,-1] > 5):
                # self.data[0,-1] = 0
            # self.data[1,-1] = 5*np.cos(self.data[0,-1])
            # self.data[2:num_data-1,-1] = np.random.rand(num_data-3)
            # now_time = time()
            # # self.data[-1,-1] = (now_time-last_time)*1e6
            # self.data[-1,-1] = 0
            # # self.data[:num_data,:] = np.hstack((self.data[:num_data,1:],dataList))
            # # self.usleep(50)
            # last_time=now_time
            # self.yieldCurrentThread()
        # print('stopped listening.')
    
    def run(self):
        self.exiting = False
        print("Listening for data...")
        while self.ser.is_open and not self.exiting:
            try:
                bytes_ready = self.ser.in_waiting
                if bytes_ready > 0:
                    # print(str(bytes_ready))
                    tempstring = self.ser.read(bytes_ready)
                    valid = tempstring.startswith(b'DB')
                    while(valid):
                        # Find how much data
                        try:
                            num_data = int(tempstring[2:4])
                            converted_floats = struct.unpack(str(num_data)+'f',tempstring[4:4+num_data*4])
                            dataList = np.array(converted_floats).reshape(num_data,1)
                            self.data[:num_data,:] = np.hstack((self.data[:num_data,1:size_arrays],dataList))
                            #print(dataList)
                            tempstring = tempstring[4+num_data*4:]
                            valid=tempstring.startswith(b'DB')
                        except ValueError:
                            print('In ListenToComThread: '+tempstring)
                            valid = False
            except serial.SerialException:
                print("Serial port "+self.ser.port+" was interrupted.")
                self.ser.close()
                self.exiting=True
            self.yieldCurrentThread()
        print('stopped listening.')

class PlotWindow(QtGui.QWidget):
    @pyqtSlot(int)
    def popupClosed(self, number_of_vars):
        print("Popup was closed")
        # Clear old data labels
        for i in range(len(self.dataLabels)):
            self.plotLegend.removeItem(self.dataLabels[i])
        # Change number of plots if needed
        if(number_of_vars != self.numPlots):
            self.numPlots = number_of_vars
            self.listener.setNumPlots(self.numPlots)
        # Set new data labels
        self.dataLabels=[]
        for i in range(self.numPlots):
            self.dataLabels.append(self.popwin.paramList[self.popwin.selectedParams[i]])
            self.plotLegend.addItem(self.plotData[i],self.dataLabels[i])
            self.plotData[i].setData(self.listener.data[i,:],name=self.dataLabels[i])
        self.timer.start()
    
    def __init__(self, maxNumPlots=10):
        super().__init__()
        self.setWindowTitle("Graph Stuff!")
        print(sys.version)
        self.maxNumPlots = maxNumPlots
        self.numPlots = maxNumPlots
        self.dataLabels = []
        self.createWindow()
        
        ## Fancy plotting things
        self.plotData = [pg.PlotDataItem() for _ in range(self.maxNumPlots)]
        self.zoomPlotData = [pg.PlotDataItem() for _ in range(self.maxNumPlots)]
        self.lr = pg.LinearRegionItem()
        self.plot.addItem(self.lr)
        self.lr.setBounds([0,size_arrays])
        self.lr.setRegion([int(size_arrays*.35),int(size_arrays*.65)])
        self.lr.sigRegionChanged.connect(self.updateZoomPlot)
        self.zoomPlot.sigXRangeChanged.connect(self.updateZoomRegion)
        for i in range(self.maxNumPlots):
            self.plot.addItem(self.plotData[i])
            self.zoomPlot.addItem(self.zoomPlotData[i])
            self.plotData[i].setPen(pg.intColor(i))
            self.zoomPlotData[i].setPen(pg.intColor(i))
        self.plotLegend = self.plot.addLegend()
        ## List the Com ports
        self.listPorts()
        
        #self.data = np.zeros(shape=(self.numPlots,size_arrays))
        #for i in range(self.numPlots):
        #   self.plotData[i].setData(self.data[i,:])
        #   self.zoomPlotData[i].setData(self.data[i,:])
        
        ## Timer stuff
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.Update)
        self.timer.start()
        
        self.plotTimer = QtCore.QTimer()
        self.plotTimer.timeout.connect(self.UpdatePlots)
        
        self.destroyed.connect(self.closeEvent)
        
        ## Create the com port listener thread
        self.listener = ListenToComThread()
        self.listener.setNumPlots(self.numPlots)

        
    def closeEvent(self, event):
        if self.ser.is_open:
            print("Closing "+self.ser.port)
            self.ser.close()
        print("Closing program")
        super().closeEvent(event)
            
    def createWindow(self):
        ## Initialize the serial port
        self.ser = serial.Serial()
        self.serstring = ''

        ## Define a top-level widget to hold everything
        
        ## Create some widgets to be placed inside
        self.serial_btn = QtGui.QPushButton('Open Serial Port')
        self.serial_btn.clicked.connect(self.OpenClicked)
        self.cmd1_button = QtGui.QPushButton('Send command:')
        self.cmd1_button.clicked.connect(self.cmd1Clicked)
        self.cmd2_button = QtGui.QPushButton('Send command:')
        self.cmd2_button.clicked.connect(self.cmd2Clicked)
        self.cmd1_text = QtGui.QLineEdit('MCU+RAMPDIR=F')
        self.cmd2_text = QtGui.QLineEdit('MCU+RAMPDIR=R')
        self.start_btn = QtGui.QPushButton('Start Comms')
        self.start_btn.clicked.connect(self.StartClicked)
        self.stop_btn = QtGui.QPushButton('Stop Comms')
        self.stop_btn.clicked.connect(self.StopClicked)
        self.listw = QtGui.QListWidget()
        self.listPortsBtn = QtGui.QPushButton('List Com Ports')
        self.listPortsBtn.clicked.connect(self.listPorts)
        self.paramsBtn = QtGui.QPushButton('Set Params')
        self.paramsBtn.clicked.connect(self.Popup)
        self.plot = pg.PlotWidget()
        self.plot.setTitle('Live Data')
        self.zoomPlot = pg.PlotWidget()
        self.zoomPlot.setTitle('Zoomed In')


        ## Create a grid layout to manage the widgets size and position
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        ## Add widgets to the layout in their proper positions
        self.layout.addWidget(self.serial_btn, 0, 0, 1, 2)
        self.layout.addWidget(self.cmd1_button, 1, 0, 1, 1)
        self.layout.addWidget(self.cmd2_button, 2, 0, 1, 1)
        self.layout.addWidget(self.cmd1_text, 1, 1, 1, 1)
        self.layout.addWidget(self.cmd2_text, 2, 1, 1, 1)
        self.layout.addWidget(self.start_btn, 3, 0, 1, 1)
        self.layout.addWidget(self.stop_btn, 3, 1, 1, 1)
        self.layout.addWidget(self.listw, 4, 0, 1, 2) 
        self.layout.addWidget(self.listPortsBtn, 5, 0, 1, 2)
        self.layout.addWidget(self.paramsBtn, 6, 0, 1, 2)
        self.layout.addWidget(self.plot, 0, 2, 7, 1)  # plot goes on right side, spanning all rows
        self.layout.addWidget(self.zoomPlot,0,3,7,1)

        ## Display the widget as a new window
        self.show()
        
    def updateZoomPlot(self):
        self.zoomPlot.setXRange(*self.lr.getRegion(),padding=0)
    def updateZoomRegion(self):
        self.lr.setRegion(self.zoomPlot.getViewBox().viewRange()[0])
    def Update(self):
        if self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    tempstring = self.ser.read(self.ser.in_waiting)
                    print(tempstring)
            except serial.SerialException:
                print("Serial port "+self.ser.port+" was interrupted.")
                self.closePort()
                
    def UpdatePlots(self):
        for i in range(self.numPlots):
            self.plotData[i].setData(self.listener.data[i,:])
            self.zoomPlotData[i].setData(self.listener.data[i,:])
    def closePort(self):
        self.ser.close()
        print("Closing "+self.ser.port)
        self.serial_btn.setText('Open Serial Port')
    def openPort(self,portName):
        print("Opening "+portName)
        self.ser.port = portName
        self.ser.open()
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.serial_btn.setText('Close Serial Port')
        self.listener.setSerialPort(self.ser)
    def listPorts(self):
        ## Fill the list widget with available serial ports
        self.listw.clear()
        genny = sorted(serial.tools.list_ports.comports())
        for id, desc, hwid in genny:
            self.listw.addItem(id)
    def OpenClicked(self):
        try:
            if(self.ser.is_open):
                self.closePort()
            else:
                self.openPort(self.listw.currentItem().text())
        except AttributeError:
            print('None')
    def StartClicked(self):
        #print(self.start_text.text())
        if(self.ser.is_open):
            # Start the run thread
            self.listener.start()
            # Stop our own updater, which consumes incoming com port data
            self.timer.stop()
            # Start the timer for updating plots
            self.plotTimer.start(50)
            self.ser.write("MCU+SERIALDATA=1\r\n".encode())
    def StopClicked(self):
        #print(self.start_text.text())
        self.listener.exit_now()
        self.plotTimer.stop()
        self.timer.start()
        if(self.ser.is_open):
            self.ser.write("MCU+SERIALDATA=0\r\n".encode())
    def cmd1Clicked(self):
        #print(self.stop_text.text())
        if(self.ser.is_open):
            tempstr = self.cmd1_text.text() + "\r\n"
            tempstr = tempstr.encode()
            self.ser.write(tempstr)
    def cmd2Clicked(self):
        #print(self.stop_text.text())
        if(self.ser.is_open):
            tempstr = self.cmd2_text.text() + "\r\n"
            tempstr = tempstr.encode()
            self.ser.write(tempstr)
        
    def Popup(self):
        # Turn off the auto-update timer. It eats up the MCU response, 
        # and we don't want that.
        self.timer.stop()
        self.popwin = PopupParamSetter(self.ser)
        self.popwin.popupClosed.connect(self.popupClosed)

class PopupParamSetter(QtGui.QWidget):
    popupClosed = pyqtSignal(int)
    
    currentDataRate = 2
    dataRates = [50,100,200,500,1000,5000]
    dialRateWindows = [0, 10, 30, 50, 70, 90, 100]
    dialDetents = [0, 20, 40, 60, 80, 99]
    
    def __init__(self, serial_port):
        super().__init__()
        self.ser = serial_port
        self.numVars = 5
        self.selectedParams = [0, 1, 2, 6, 10, 0, 0, 0, 0, 0]

        self.createWindow()

    def createWindow(self):
        self.layout = QtGui.QGridLayout()
        self.setWindowTitle("Please wait...")
        self.setLayout(self.layout)
        
        self.labelChooseNumVars = QtGui.QLabel('Number of variables')
        self.NumVarSpin = QtGui.QSpinBox()
        self.NumVarSpin.setMinimum(1)
        self.NumVarSpin.setMaximum(10)
        self.NumVarSpin.setValue(self.numVars)
        self.DataRateLabel = QtGui.QLabel('Data Rate: '+str(self.dataRates[self.currentDataRate])+'Hz')
        self.DataRateDial = QtGui.QDial()
        self.DataRateDial.setMinimum(0)
        self.DataRateDial.setMaximum(99)
        self.DataRateDial.setValue(self.dialDetents[self.currentDataRate])
        self.layout.addWidget(self.labelChooseNumVars,0,0,1,1)
        self.layout.addWidget(self.NumVarSpin,0,1,1,1)
        self.layout.addWidget(self.DataRateLabel,1,0,1,1)
        self.layout.addWidget(self.DataRateDial,1,1,1,1)
        
        self.NumVarSpin.valueChanged.connect(self.SpinBoxChanged)
        self.DataRateDial.valueChanged.connect(self.DialChanged)
        self.DataRateDial.sliderReleased.connect(self.DialDetent)
        self.DataRateDial.setMinimumSize(150,150)

        
        self.Combos = [QtGui.QComboBox() for _ in range(10)]
        self.Labels = [QtGui.QLabel(str) for str in ['Param1','Param2',\
        'Param3','Param4','Param5','Param6','Param7','Param8','Param9','Param10']]
        self.OkButton = QtGui.QPushButton('OK')
        self.CancelButton = QtGui.QPushButton('Cancel')
        self.CancelButton.clicked.connect(self.close)
        self.layout.addWidget(self.OkButton,12,0,1,1)
        self.layout.addWidget(self.CancelButton,12,1,1,1)
        
        for i in range(10):
            self.layout.addWidget(self.Labels[i],i+2,0)
            self.layout.addWidget(self.Combos[i],i+2,1)

        for i in range(10-self.numVars):
            self.Labels[i+self.numVars].hide()
            self.Combos[i+self.numVars].hide()
        self.timeoutTimer = QtCore.QTimer()
        if self.ser.is_open:
            self.ser.write("MCU+USB?\r\n".encode())
        self.timeoutTimer.timeout.connect(self.createParamList)
        self.timeoutTimer.start(25)
        self.show()
        
    def createParamList(self):
        self.timeoutTimer.stop()
        self.timeoutTimer.timeout.disconnect(self.createParamList)
        self.codes = []
        self.descs = []
        if self.ser.is_open:
            if self.ser.in_waiting > 0:
                # Read the entire response
                read_all_string = self.ser.read(self.ser.in_waiting).decode('utf-8')
                # print(read_all_string)
                # Parse through, extract codes and descriptions
                indiv_lines = read_all_string.split('\n')
                # print(indiv_lines)
                for line in indiv_lines:
                    print(line)
                    if((not line.startswith('MCU')) and (line)):
                        numpart, rest = line.split(':')
                        linenum = int(numpart)
                        code, desc = rest.strip().split(',')
                        code = code.strip()
                        desc = desc.strip()
                        self.codes.append(code)
                        self.descs.append(desc)
        self.setSpinner()
        # Listen for the number of variables currently set in the controller
        if self.ser.is_open:
            self.ser.write("MCU+USBNUMVARS?\r\n".encode())

        self.timeoutTimer.timeout.connect(self.cb_numVars)
        self.timeoutTimer.start(25)
    def cb_numVars(self):
        self.timeoutTimer.stop()
        self.timeoutTimer.timeout.disconnect(self.cb_numVars)
            
        if self.ser.is_open:
            if self.ser.in_waiting > 0:
                # Read it all in
                read_all_string = self.ser.read(self.ser.in_waiting).decode('utf-8')
                indiv_lines = read_all_string.split('\n')
                # print(indiv_lines)
                for line in indiv_lines:
                    print(line)
                    if((not line.startswith('MCU')) and (line)):
                        try:
                            self.numVars = int(line)
                        except ValueError:
                            print("In popupParamSetter: "+line)
            self.NumVarSpin.setValue(self.numVars)
            self.SpinBoxChanged()
            self.ser.write("MCU+USBSPEED?\r\n".encode())
            
        self.timeoutTimer.timeout.connect(self.cb_speed)
        self.timeoutTimer.start(25)
    def cb_speed(self):
        self.timeoutTimer.stop()
        self.timeoutTimer.timeout.disconnect(self.cb_speed)
        if self.ser.is_open:
            if self.ser.in_waiting > 0:
                # Read it all in
                read_all_string = self.ser.read(self.ser.in_waiting).decode('utf-8')
                indiv_lines = read_all_string.split('\n')
                #print(indiv_lines)
                for line in indiv_lines:
                    print(line)
                    if((not line.startswith('MCU')) and (line)):
                        try:
                            self.currentDataRate = int(line)
                            self.DataRateDial.setValue(self.dialDetents[self.currentDataRate])
                            self.DialChanged()
                        except ValueError:
                            print("In popupParamSetter: "+line)
            self.NumVarSpin.setValue(self.numVars)
            self.SpinBoxChanged()
            self.ser.write("MCU+USBSPEED?\r\n".encode())

    def setSpinner(self):
        if(len(self.codes) == 0):
            self.paramList = ['Ia','Ib','Ic','Ta','Tb','Tc','Throttle','RampAngle',\
            'HallAngle','HallSpeed','Vbus','Id','Iq','Td','Tq','ErrorCode',\
            'Vrefint']
            self.paramSendList = ['IA','IB','IC','TA','TB','TC','TH','RA','HA',\
            'HS','VS','ID','IQ','TD','TQ','ER','VR']
        else:
            self.paramList = self.descs
            self.paramSendList = self.codes
        
        for i in range(10):
            for j in range(len(self.paramList)):
                self.Combos[i].insertItem(j,self.paramList[j])
        
        self.OkButton.clicked.connect(self.submitValues)
        self.setWindowTitle("Set Params!")
    def closeEvent(self, event):
        # self.closeSig.closeSignal()
        self.popupClosed.emit(self.numVars)
        super().closeEvent(event)
    def submitValues(self):
        if self.ser.is_open:
            print('Number of variables: '+str(self.numVars))
            self.ser.write('MCU+USBNUMVARS='.encode()+str(self.numVars).encode()+'\r\n'.encode())
            self.timeoutTimer.timeout.connect(self.submitStep2)
            self.timeoutTimer.start(25)
        else:
            self.close()
    def submitStep2(self):
        self.timeoutTimer.stop()
        self.timeoutTimer.timeout.disconnect(self.submitStep2)
        print('Speed: '+str(self.currentDataRate))
        self.ser.write('MCU+USBSPEED='.encode()+str(self.currentDataRate).encode()+'\r\n'.encode())
        self.timeoutTimer.timeout.connect(self.submitStep3)
        self.timeoutTimer.start(25)
        
    def submitStep3(self):
        self.timeoutTimer.stop()
        self.timeoutTimer.timeout.disconnect(self.submitStep3)
        for i in range(self.numVars):
            self.selectedParams[i] = self.Combos[i].currentIndex()
            print("Param "+str(i)+": "+str(self.selectedParams[i]))
            sendStr = "MCU+USB="+self.paramSendList[self.selectedParams[i]]+","+str(i+1)+"\r\n"
            sendStr = sendStr.encode()
            self.ser.write(sendStr)
        self.close()
    def SpinBoxChanged(self):
        # Remove all dropdowns
        for i in range(10):
            self.Labels[i].hide()
            self.Combos[i].hide()
        self.numVars = self.NumVarSpin.value()
        for i in range(self.numVars):
            self.Labels[i].show()
            self.Combos[i].show()
    def DialChanged(self):
        #print(self.DataRateDial.value())
        dialVal = self.DataRateDial.value()
        dataRate = -1
        for i in range(len(self.dataRates)):
            if((dialVal >= self.dialRateWindows[i]) and (dialVal < self.dialRateWindows[i+1])):
                dataRate = i
#                self.DataRateDial.setValue(int((self.dialRateWindows[i]+self.dialRateWindows[i+1])/2))
        #print(dataRate)
        if(dataRate != -1):
            self.currentDataRate = dataRate
            self.DataRateLabel.setText('Data Rate: '+str(self.dataRates[self.currentDataRate])+ 'Hz')
    def DialDetent(self):
        self.DataRateDial.setValue(self.dialDetents[self.currentDataRate])



def main():
    ## Always start by initializing Qt (only once per application)
    app = QtGui.QApplication(sys.argv)
    plotWin = PlotWindow()
    ## Start the Qt event loop
    sys.exit(app.exec_())

## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    main()
#    import sys
#    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
#        QtGui.QApplication.instance().exec_()
