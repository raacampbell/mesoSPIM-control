'''
mesoSPIM MainWindow

'''
import sys
import copy

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.uic import loadUi

from .mesoSPIM_CameraWindow import mesoSPIM_CameraWindow
from .mesoSPIM_AcquisitionManagerWindow import mesoSPIM_AcquisitionManagerWindow
from .mesoSPIM_ScriptWindow import mesoSPIM_ScriptWindow

from .mesoSPIM_State import mesoSPIM_StateModel
from .mesoSPIM_Core import mesoSPIM_Core
from .devices.joysticks.mesoSPIM_JoystickHandlers import mesoSPIM_JoystickHandler

class mesoSPIM_MainWindow(QtWidgets.QMainWindow):
    '''
    Main application window which instantiates worker objects and moves them
    to a thread.
    '''
    # sig_live = QtCore.pyqtSignal()
    sig_stop = QtCore.pyqtSignal()

    sig_finished = QtCore.pyqtSignal()

    sig_enable_gui = QtCore.pyqtSignal()

    sig_state_request = QtCore.pyqtSignal(dict)
    sig_state_model_request = QtCore.pyqtSignal(dict)
    sig_state_changed = QtCore.pyqtSignal(dict)

    sig_execute_script = QtCore.pyqtSignal(str)

    sig_move_relative = QtCore.pyqtSignal(dict)
    sig_move_relative_and_wait_until_done = QtCore.pyqtSignal(dict)
    sig_move_absolute = QtCore.pyqtSignal(dict)
    sig_move_absolute_and_wait_until_done = QtCore.pyqtSignal(dict)
    sig_zero_axes = QtCore.pyqtSignal(list)
    sig_unzero_axes = QtCore.pyqtSignal(list)
    sig_stop_movement = QtCore.pyqtSignal()
    sig_load_sample = QtCore.pyqtSignal()
    sig_unload_sample = QtCore.pyqtSignal()

    def __init__(self, config=None):
        super().__init__()

        '''
        Initial housekeeping
        '''

        self.cfg = config
        self.script_window_counter = 0
        self.update_gui_from_state_flag = False

        ''' Instantiate the one and only mesoSPIM state '''
        self.state_model = mesoSPIM_StateModel(self)
        self.state_model_mutex = QtCore.QMutex()
        self.sig_state_model_request.connect(self.state_model.set_state)
        self.state_model.sig_state_model_updated.connect(self.update_gui_from_state)

        '''
        Setting up the user interface windows
        '''

        loadUi('gui/mesoSPIM_MainWindow.ui', self)
        self.setWindowTitle('mesoSPIM Main Window')

        self.camera_window = mesoSPIM_CameraWindow()
        self.camera_window.show()

        self.acquisition_manager_window = mesoSPIM_AcquisitionManagerWindow(self)
        self.acquisition_manager_window.show()

        '''
        Setting up the threads
        '''

        ''' Setting the mesoSPIM_Core thread up '''
        self.core_thread = QtCore.QThread()
        self.core = mesoSPIM_Core(self.cfg, self)
        self.core.moveToThread(self.core_thread)

        ''' Get buttons & connections ready '''
        self.initialize_and_connect_widgets()

        ''' Widget list for blockSignals during status updates '''
        self.widgets_to_block = []
        self.parent_widgets_to_block = [self.ETLTabWidget, self.ParameterTabWidget, self.ControlGroupBox]
        self.create_widget_list(self.parent_widgets_to_block, self.widgets_to_block)

        # self.WidgetListPushButton.clicked.connect(self.create_widget_list)

        ''' The signal switchboard '''
        self.core.sig_finished.connect(lambda: self.sig_finished.emit())
        self.core.sig_finished.connect(self.enable_gui)

        self.core.sig_state_model_request.connect(lambda dict: self.sig_state_model_request.emit(dict))
        self.core.sig_state_model_request.connect(self.update_position_indicators)
        self.core.sig_update_gui_from_state.connect(self.set_update_gui_from_state_flag)
                
        self.core.sig_progress.connect(self.update_progressbars)

        ''' Start the thread '''
        self.core_thread.start()

        ''' Setting up the joystick '''
        self.joystick = mesoSPIM_JoystickHandler(self)

        ''' Connecting the camera frames (this is a deep connection and slightly
        risky) It will break immediately when there is an API change.'''
        try:
            self.core.camera_worker.sig_camera_frame.connect(self.camera_window.set_image)
            print('Camera connected successfully to the display window!')
        except:
            print('Warning: camera not connected to display!')

    def __del__(self):
        '''Cleans the threads up after deletion, waits until the threads
        have truly finished their life.

        Make sure to keep this up to date with the number of threads
        '''
        try:
            self.core_thread.quit()
            self.core_thread.wait()
        except:
            pass

    def check_instances(self, widget):
        ''' 
        Method to check whether a widget belongs to one of the Qt Classes specified.

        Args:
            widget (QtWidgets.QWidget): Widget to check 

        Returns:
            return_value (bool): True if widget is in the list, False if not.
        '''
        if isinstance(widget, (QtWidgets.QSpinBox, 
                                QtWidgets.QDoubleSpinBox,
                                QtWidgets.QSlider,
                                QtWidgets.QComboBox,
                                QtWidgets.QPushButton)):
            return True 
        else:
            return False

    def create_widget_list(self, list, widget_list):
        '''
        Helper method to recursively loop through all the widgets in a list and 
        their children.

        Args:
            list (list): List of QtWidgets.QWidget objects 
        
        '''
        for widget in list:
            if list != ([] or None):
                if self.check_instances(widget):
                    # print(widget.objectName())
                    widget_list.append(widget)
                list = widget.children()
                self.create_widget_list(list, widget_list)
            else:
                return None

    @QtCore.pyqtSlot(str)
    def display_status_message(self, string, time=0):
        '''
        Displays a message in the status bar for a time in ms

        If time=0, the message will stay.
        '''

        if time == 0:
            self.statusBar().showMessage(string)
        else:
            self.statusBar().showMessage(string, time)

    def get_state_parameter(self, parameter_string):
        '''
        Helper method to get a parameter out of the state model:
        '''
        return self.state_model.state[parameter_string]

    def pos2str(self, position):
        ''' Little helper method for converting positions to strings '''

        ''' Show 2 decimal places '''
        return '%.2f' % position

    @QtCore.pyqtSlot(dict)
    def update_position_indicators(self, dict):
        for key, pos_dict in dict.items():
            if key == 'position':
                self.X_Position_Indicator.setText(self.pos2str(pos_dict['x_pos'])+' µm')
                self.Y_Position_Indicator.setText(self.pos2str(pos_dict['y_pos'])+' µm')
                self.Z_Position_Indicator.setText(self.pos2str(pos_dict['z_pos'])+' µm')
                self.Focus_Position_Indicator.setText(self.pos2str(pos_dict['f_pos'])+' µm')
                self.Rotation_Position_Indicator.setText(self.pos2str(pos_dict['theta_pos'])+'°')

    @QtCore.pyqtSlot(dict)
    def update_progressbars(self,dict):
        cur_acq = dict['current_acq']
        tot_acqs = dict['total_acqs']
        cur_image = dict['current_image_in_acq']
        images_in_acq = dict['images_in_acq']
        tot_images = dict['total_image_count']
        image_count = dict['image_counter']

        self.AcquisitionProgressBar.setValue(int((cur_image+1)/images_in_acq*100))
        self.TotalProgressBar.setValue(int((image_count+1)/tot_images*100))

        self.AcquisitionProgressBar.setFormat('%p% (Image '+ str(cur_image+1) +\
                                        '/' + str(images_in_acq) + ')')
        self.TotalProgressBar.setFormat('%p% (Acquisition '+ str(cur_acq+1) +\
                                        '/' + str(tot_acqs) +\
                                         ')' + ' (Image '+ str(image_count) +\
                                        '/' + str(tot_images) + ')')

    def create_script_window(self):
        '''
        Creates a script window and binds it to a self.scriptwindow0 ... n instanceself.

        This happens dynamically using exec which should be replaced at
        some point with a factory pattern.
        '''
        windowstring = 'self.scriptwindow'+str(self.script_window_counter)
        exec(windowstring+ '= mesoSPIM_ScriptWindow(self)')
        exec(windowstring+'.setWindowTitle("Script Window #'+str(self.script_window_counter)+'")')
        exec(windowstring+'.show()')
        exec(windowstring+'.sig_execute_script.connect(self.execute_script)')
        self.script_window_counter += 1

    def initialize_and_connect_widgets(self):
        ''' Connecting the menu actions '''
        self.openScriptEditorButton.clicked.connect(self.create_script_window)

        ''' Connecting the movement & zero buttons '''
        self.xPlusButton.pressed.connect(lambda: self.sig_move_relative.emit({'x_rel': self.xyzIncrementSpinbox.value()}))
        self.xMinusButton.pressed.connect(lambda: self.sig_move_relative.emit({'x_rel': -self.xyzIncrementSpinbox.value()}))
        self.yPlusButton.pressed.connect(lambda: self.sig_move_relative.emit({'y_rel': self.xyzIncrementSpinbox.value()}))
        self.yMinusButton.pressed.connect(lambda: self.sig_move_relative.emit({'y_rel': -self.xyzIncrementSpinbox.value()}))
        self.zPlusButton.pressed.connect(lambda: self.sig_move_relative.emit({'z_rel': self.xyzIncrementSpinbox.value()}))
        self.zMinusButton.pressed.connect(lambda: self.sig_move_relative.emit({'z_rel': -self.xyzIncrementSpinbox.value()}))
        self.focusPlusButton.pressed.connect(lambda: self.sig_move_relative.emit({'f_rel': self.focusIncrementSpinbox.value()}))
        self.focusMinusButton.pressed.connect(lambda: self.sig_move_relative.emit({'f_rel': -self.focusIncrementSpinbox.value()}))
        self.rotPlusButton.pressed.connect(lambda: self.sig_move_relative.emit({'theta_rel': self.rotIncrementSpinbox.value()}))
        self.rotMinusButton.pressed.connect(lambda: self.sig_move_relative.emit({'theta_rel': -self.rotIncrementSpinbox.value()}))

        self.xyzrotStopButton.pressed.connect(self.sig_stop_movement.emit)

        self.xyZeroButton.toggled.connect(lambda bool: print('XY toggled') if bool is True else print('XY detoggled'))
        self.xyZeroButton.clicked.connect(lambda bool: self.sig_zero_axes.emit(['x','y']) if bool is True else self.sig_unzero_axes.emit(['x','y']))
        self.zZeroButton.clicked.connect(lambda bool: self.sig_zero_axes.emit(['z']) if bool is True else self.sig_unzero_axes.emit(['z']))
        # self.xyzZeroButton.clicked.connect(lambda bool: self.sig_zero.emit(['x','y','z']) if bool is True else self.sig_unzero.emit(['x','y','z']))
        self.focusZeroButton.clicked.connect(lambda bool: self.sig_zero_axes.emit(['f']) if bool is True else self.sig_unzero_axes.emit(['f']))
        self.rotZeroButton.clicked.connect(lambda bool: self.sig_zero_axes.emit(['theta']) if bool is True else self.sig_unzero_axes.emit(['theta']))
        #
        self.xyzLoadButton.clicked.connect(self.sig_load_sample.emit)
        self.xyzUnloadButton.clicked.connect(self.sig_unload_sample.emit)

        self.LiveButton.clicked.connect(self.live)
        self.StopButton.clicked.connect(lambda: self.sig_state_request.emit({'state':'idle'}))
        self.StopButton.clicked.connect(lambda: print('Stopping'))

        self.widget_to_state_parameter_assignment=(
            (self.FilterComboBox, 'filter',1),
            (self.FilterComboBox, 'filter',1),
            (self.ZoomComboBox, 'zoom',1),
            (self.ShutterComboBox, 'shutterconfig',1),
            (self.LaserComboBox, 'laser',1),
            (self.LaserIntensitySlider, 'intensity',1),
            (self.CameraExposureTimeSpinBox, 'camera_exposure_time',1000),
            (self.CameraLineIntervalSpinBox,'camera_line_interval',1000000),
            (self.SweeptimeSpinBox,'sweeptime',1000),
            (self.LeftLaserPulseDelaySpinBox,'laser_l_delay_%',1),
            (self.RightLaserPulseDelaySpinBox,'laser_r_delay_%',1),
            (self.LeftLaserPulseLengthSpinBox,'laser_l_pulse_%',1),
            (self.RightLaserPulseLengthSpinBox,'laser_r_pulse_%',1),
            (self.LeftLaserPulseMaxAmplitudeSpinBox,'laser_l_max_amplitude_%',1),
            (self.RightLaserPulseMaxAmplitudeSpinBox,'laser_r_max_amplitude_%',1),
            (self.GalvoFrequencySpinBox,'galvo_r_frequency',1),
            (self.GalvoFrequencySpinBox,'galvo_l_frequency',1),
            (self.LeftGalvoAmplitudeSpinBox,'galvo_l_amplitude',1),
            (self.LeftGalvoAmplitudeSpinBox,'galvo_r_amplitude',1),
            (self.LeftGalvoPhaseSpinBox,'galvo_l_phase',1),
            (self.RightGalvoPhaseSpinBox,'galvo_r_phase',1),
            (self.LeftGalvoOffsetSpinBox, 'galvo_l_offset',1),
            (self.RightGalvoOffsetSpinBox, 'galvo_r_offset',1),
            (self.LeftETLOffsetSpinBox,'etl_l_offset',1),
            (self.RightETLOffsetSpinBox,'etl_r_offset',1),
            (self.LeftETLAmplitudeSpinBox,'etl_l_amplitude',1),
            (self.RightETLAmplitudeSpinBox,'etl_r_amplitude',1),
            (self.LeftETLDelaySpinBox,'etl_l_delay_%',1),
            (self.RightETLDelaySpinBox,'etl_r_delay_%',1),
            (self.LeftETLRampRisingSpinBox,'etl_l_ramp_rising_%',1),
            (self.RightETLRampRisingSpinBox, 'etl_r_ramp_rising_%',1),
            (self.LeftETLRampFallingSpinBox, 'etl_l_ramp_falling_%',1),
            (self.RightETLRampFallingSpinBox, 'etl_r_ramp_falling_%',1)
        )

        for widget, state_parameter, conversion_factor in self.widget_to_state_parameter_assignment:
            self.connect_widget_to_state_parameter(widget, state_parameter, conversion_factor)

        ''' Connecting the microscope controls '''
        self.connect_combobox_to_state_parameter(self.FilterComboBox,self.cfg.filterdict.keys(),'filter')
        self.connect_combobox_to_state_parameter(self.ZoomComboBox,self.cfg.zoomdict.keys(),'zoom')
        self.connect_combobox_to_state_parameter(self.ShutterComboBox,self.cfg.shutteroptions,'shutterconfig')
        self.connect_combobox_to_state_parameter(self.LaserComboBox,self.cfg.laserdict.keys(),'laser')

        self.LaserIntensitySlider.valueChanged.connect(lambda currentValue: self.sig_state_request.emit({'intensity': currentValue}))
        self.LaserIntensitySlider.setValue(self.cfg.startup['intensity'])

        for widget, state_parameter, conversion_factor in self.widget_to_state_parameter_assignment:
            self.connect_widget_to_state_parameter(widget, state_parameter, conversion_factor)

    def connect_widget_to_state_parameter(self, widget, state_parameter, conversion_factor):
        '''
        Helper method to (currently) connect spinboxes
        '''
        if isinstance(widget,(QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            self.connect_spinbox_to_state_parameter(widget, state_parameter, conversion_factor)

    def connect_combobox_to_state_parameter(self, combobox, option_list, state_parameter):
        '''
        Helper method to connect and initialize a combobox from the config

        Args:
            combobox (QtWidgets.QComboBox): Combobox in the GUI to be connected
            option_list (list): List of selection options
            state_parameter (str): State parameter (has to exist in the config)
        '''
        combobox.addItems(option_list)
        combobox.currentTextChanged.connect(lambda currentText: self.sig_state_request.emit({state_parameter : currentText}))
        combobox.setCurrentText(self.cfg.startup[state_parameter])

    def connect_spinbox_to_state_parameter(self, spinbox, state_parameter, conversion_factor=1):
        '''
        Helper method to connect and initialize a spinbox from the config

        Args:
            spinbox (QtWidgets.QSpinBox or QtWidgets.QDoubleSpinbox): Spinbox in
                    the GUI to be connected
            state_parameter (str): State parameter (has to exist in the config)
            conversion_factor (float): Conversion factor. If the config is in
                                       seconds, the spinbox displays ms:
                                       conversion_factor = 1000. If the config is
                                       in seconds and the spinbox displays
                                       microseconds: conversion_factor = 1000000
        '''
        spinbox.valueChanged.connect(lambda currentValue: self.sig_state_request.emit({state_parameter : currentValue/conversion_factor}))
        spinbox.setValue(self.cfg.startup[state_parameter]*conversion_factor)

    @QtCore.pyqtSlot(str)
    def execute_script(self, script):
        #self.enable_external_gui_updates = True
        #self.block_signals_from_controls(True)
        self.sig_execute_script.emit(script)

    def block_signals_from_controls(self, bool):
        '''
        Helper method to allow blocking of signals from all kinds of controls.

        Needs a list in self.widgets_to_block which has to be created during 
        mesoSPIM_MainWindow.__init__()
        
        Args:
            bool (bool): True if widgets are supposed to be blocked, False if unblocking is desired.
        '''
        for widget in self.widgets_to_block:
            widget.blockSignals(bool)

    def update_widget_from_state(self, widget, state_parameter_string, conversion_factor):
        if isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(self.get_state_parameter(state_parameter_string))
        elif isinstance(widget, (QtWidgets.QSlider,QtWidgets.QDoubleSpinBox,QtWidgets.QSpinBox)):
            widget.setValue(self.get_state_parameter(state_parameter_string)*conversion_factor)

    @QtCore.pyqtSlot(bool)
    def set_update_gui_from_state_flag(self, bool):
        self.update_gui_from_state_flag = bool


    def update_gui_from_state(self):
        '''
        Updates the GUI controls after a state_change
        if the self.update_gui_from_state_flag is enabled.
        '''
        if self.update_gui_from_state_flag:
            self.block_signals_from_controls(True)
            with QtCore.QMutexLocker(self.state_model_mutex):
                for widget, state_parameter, conversion_factor in self.widget_to_state_parameter_assignment:
                    self.update_widget_from_state(widget, state_parameter, conversion_factor)                
            self.block_signals_from_controls(False)
        
    def live(self):
        print('Going live')
        self.sig_state_request.emit({'state':'live'})

    def disable_gui(self):
        pass

    def enable_gui(self):
        self.enable_external_gui_updates = False
        self.block_signals_from_controls(False)
