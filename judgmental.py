# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SamplingTime
                                 A QGIS plugin
 A comprehensive QGIS plugin for automated area sampling using judgmental,
 random, systematic, stratified, and cluster techniques. It enables the 
 creation of sampling areas, exclusion zones, customizable stratification 
 and clustering, and generates shapefiles for outputs. Designed for precision 
 and adaptability in geospatial workflows.
 -------------------
        begin                : 2024-09-29
        copyright            : (C) 2024 by Marcel A. Cedrez
        email                : marcel.a@giscourse.online
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This file is part of Sampling Time Plugin for QGIS.                   *
 *                                                                         *
 *   Sampling Time Plugin is free software: you can redistribute it and/or *
 *   modify it under the terms of the GNU General Public License as        *
 *   published by the Free Software Foundation, either version 3 of the    *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   Sampling Time Plugin is distributed in the hope that it will be       *
 *   useful, but WITHOUT ANY WARRANTY; without even the implied warranty   *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the       *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with Sampling Time Plugin. If not, see                         *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/
"""

# Importing Python libraries for file handling, CSV, data manipulation, and QGIS components
import os
import csv
import pandas as pd
from qgis.PyQt.QtWidgets import (
   QMessageBox, QFileDialog, QInputDialog, QAction
)
from qgis.core import (
   QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
   QgsPointXY, QgsField, QgsSymbol, QgsSingleSymbolRenderer,
   QgsVectorFileWriter, QgsSvgMarkerSymbolLayer,
   QgsFeatureRequest
)
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt, QVariant


class JudgmentalSampling:
    def __init__(self, iface, dialog):
        # Constructor for JudgmentalSampling class, initializes necessary variables and widgets
        self.iface = iface
        self.dialog = dialog
        self.canvas = iface.mapCanvas()
        self.sample_count = 0
        self.temp_layer = None
        self.map_tool = None
        self.sampling_area = None
        self.exclusion_zones = []
        self.sample_order = []
        self.coordinates_list = []
        self.sampling_method = None
        self.allow_outside_sampling = False
        self.manual_editing_active = False
        self.file_data = None
        self.selected_x_column = None
        self.selected_y_column = None
        self.file_sampling_message_shown = False

        # Connecting signals to buttons and checkboxes
        self.dialog.pushButtonaddcoordinates_judgmental.clicked.connect(
            lambda: self.add_coordinates())
        self.dialog.pushButtonfinishcoordinates_judgmental.clicked.connect(
            lambda: self.finish_coordinates())
        self.dialog.listWidgetlistofcoordinates_judgmental.itemDoubleClicked.connect(
            self.remove_coordinate)
        self.dialog.checkBoxaddsamplesmanually.stateChanged.connect(
            self.toggle_manual_sampling)
        self.dialog.checkBoxaddsamplesbycoordinates.stateChanged.connect(
            self.toggle_coordinate_sampling)
        self.dialog.checkBoxaddsamplesbyfile.stateChanged.connect(
            self.toggle_file_sampling)
        self.dialog.checkBoxoutsidesampling.stateChanged.connect(
            self.update_allow_outside_sampling)
        self.dialog.pushButtonloadfilejudgmental.clicked.connect(
            self.load_file)
        self.dialog.pushButtonaddcoordinatesfile_judgmental.clicked.connect(
            self.add_coordinates_from_file)
        self.dialog.pushButtonfinishcoordinatesfile_judgmental.clicked.connect(
            self.finish_sampling_by_file)

        QgsProject.instance().layerRemoved.connect(self.handle_layer_removed)

    def is_temp_layer_valid(self):
        # Checks if the temporary layer exists and is present in the QGIS project
        try:
            return self.temp_layer is not None and QgsProject.instance().mapLayer(self.temp_layer.id()) is not None
        except RuntimeError:
            self.temp_layer = None
            return False

    def update_allow_outside_sampling(self, state):
        # Updates the flag indicating if points can be placed outside the sampling area
        self.allow_outside_sampling = (state == Qt.Checked)

    def toggle_manual_sampling(self, state):
        # Toggles the manual sampling mode (adding points directly on the map)
        try:
            if state == Qt.Checked:
                if not self.dialog.comboBoxshpsampling.currentText():
                    QMessageBox.warning(
                        self.dialog, "Error", "No shapefile has been loaded/selected as the sampling area.")
                    self.dialog.checkBoxaddsamplesmanually.setChecked(False)
                    return
                self.dialog.checkBoxaddsamplesbycoordinates.setChecked(False)
                self.dialog.checkBoxaddsamplesbyfile.setChecked(False)
                self.dialog.pushButtonedition.setEnabled(True)
                self.dialog.pushButtonfinishedition.setEnabled(False)
                QMessageBox.information(self.dialog, "Manual Sampling",
                                        "Click 'Start' to begin adding sample points on the map. Left-click to add points and right-click to remove them. When finished, click 'Finish' to generate the final shapefile.")
            else:
                try:
                    self.stop_sampling()
                except:
                    pass
                self.dialog.checkBoxaddsamplesbycoordinates.setEnabled(True)
                self.dialog.checkBoxaddsamplesbyfile.setEnabled(True)
                self.dialog.pushButtonedition.setEnabled(False)
                self.dialog.pushButtonfinishedition.setEnabled(False)
        except Exception as e:
            print(f"Error in toggle_manual_sampling: {str(e)}")

    def toggle_coordinate_sampling(self, state):
        # Toggles the coordinate sampling mode (adding points by entering X/Y or clicking on the map)
        if state == Qt.Checked:
            if not self.dialog.comboBoxshpsampling.currentText():
                QMessageBox.warning(
                    self.dialog, "Error", "No shapefile has been loaded/selected as the sampling area.")
                self.dialog.checkBoxaddsamplesbycoordinates.setChecked(False)
                return
            self.dialog.checkBoxaddsamplesmanually.setChecked(False)
            self.dialog.checkBoxaddsamplesbyfile.setChecked(False)
            self.start_coordinate_sampling()
            self.dialog.pushButtonfinishcoordinates_judgmental.setEnabled(True)
        else:
            self.dialog.checkBoxaddsamplesmanually.setEnabled(True)
            self.dialog.checkBoxaddsamplesbyfile.setEnabled(True)
            self.stop_sampling()
            self.dialog.pushButtonfinishcoordinates_judgmental.setEnabled(False)

    def toggle_file_sampling(self, state):
        # Toggles the file sampling mode (adding points from a file, or manually if desired)
        if state == Qt.Checked:
            if not self.dialog.comboBoxshpsampling.currentText():
                QMessageBox.warning(
                    self.dialog, "Error", "No shapefile has been loaded/selected as the sampling area.")
                self.dialog.checkBoxaddsamplesbyfile.setChecked(False)
                return
            self.dialog.checkBoxaddsamplesmanually.setChecked(False)
            self.dialog.checkBoxaddsamplesbycoordinates.setChecked(False)
            self.start_file_sampling()
            self.dialog.pushButtonfinishcoordinatesfile_judgmental.setEnabled(True)
        else:
            self.dialog.checkBoxaddsamplesmanually.setEnabled(True)
            self.dialog.checkBoxaddsamplesbycoordinates.setEnabled(True)
            self.stop_sampling()
            self.dialog.pushButtonfinishcoordinatesfile_judgmental.setEnabled(False)

    def start_editing(self, allow_outside_sampling=False):
        # Begins the manual editing process, setting the appropriate flags and map tool
        if self.manual_editing_active:
            return
        self.sampling_method = 'manual'
        self.allow_outside_sampling = allow_outside_sampling
        self.manual_editing_active = True
        if not self.initialize_sampling():
            self.manual_editing_active = False
            return
        if not self.map_tool:
            self.map_tool = SamplingMapTool(self.canvas, self)
        self.canvas.setMapTool(self.map_tool)
        self.dialog.pushButtonfinishedition.setEnabled(True)
        self.dialog.pushButtonedition.setEnabled(False)

    def start_coordinate_sampling(self):
        # Initializes coordinate sampling, allowing users to enter coordinates or click on the map
        self.sampling_method = 'coordinates'
        if not self.initialize_sampling():
            return
        if not self.map_tool:
            self.map_tool = SamplingMapTool(self.canvas, self)
        self.canvas.setMapTool(self.map_tool)
        QMessageBox.information(
            self.dialog,
            "Coordinate Sampling",
            "To add sample points, enter the X and Y coordinates and click 'Add Coordinates', or simply left-click on the map to place points and right-click to remove them. When you're done, click 'Finish' to create the final shapefile."
        )

    def start_file_sampling(self):
        # Initializes file sampling, allowing users to load a file of coordinates, or add points manually
        self.sampling_method = 'file'
        if not self.initialize_sampling():
            return
        if not self.map_tool:
            self.map_tool = SamplingMapTool(self.canvas, self)
        self.canvas.setMapTool(self.map_tool)
        if not self.file_sampling_message_shown:
            QMessageBox.information(
                self.dialog,
                "File Sampling",
                "To load sample points, use the 'Load File' button to select a CSV or XLSX file. Choose the X and Y coordinate columns and click 'Add Coordinates' to place them on the map. You can also left-click on the map to add points manually and right-click to remove them. When you're done, click 'Finish' to create the final shapefile."
            )
            self.file_sampling_message_shown = True

    def stop_sampling(self):
        # Cleans up after sampling is stopped, removing temp layers and resetting states
        try:
            self.manual_editing_active = False
            if self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
                self.map_tool = None
            if self.is_temp_layer_valid():
                QgsProject.instance().removeMapLayer(self.temp_layer.id())
            self.temp_layer = None
            self.sample_count = 0
            self.sample_order.clear()
            self.dialog.listWidgetlistofcoordinates_judgmental.clear()
            self.file_data = None
            self.selected_x_column = None
            self.selected_y_column = None
            self.dialog.lineEditaddsamplesbyfile.clear()
            self.dialog.comboBoxcolumnx.clear()
            self.dialog.comboBoxcolumny.clear()
            self.dialog.pushButtonfinishedition.setEnabled(False)
            self.dialog.pushButtonfinishcoordinates_judgmental.setEnabled(False)
            self.dialog.pushButtonfinishcoordinatesfile_judgmental.setEnabled(False)
            self.dialog.pushButtonedition.setEnabled(True)
            self.dialog.pushButtonloadfilejudgmental.setEnabled(False)
            self.dialog.pushButtonaddcoordinatesfile_judgmental.setEnabled(False)
            self.dialog.comboBoxcolumnx.setEnabled(False)
            self.dialog.comboBoxcolumny.setEnabled(False)
            self.file_sampling_message_shown = False
        except Exception as e:
            print(f"Error in stop_sampling: {str(e)}")
            self.temp_layer = None
            self.dialog.pushButtonedition.setEnabled(True)
            self.dialog.pushButtonfinishedition.setEnabled(False)

    def finish_editing(self):
        # Finishes manual editing by generating and saving the shapefile
        if not self.is_temp_layer_valid():
            QMessageBox.warning(self.dialog, "No Samples",
                                "No samples have been added or the temporary layer has been deleted.")
            self.stop_sampling()
            return
        if not self.temp_layer or self.temp_layer.featureCount() == 0:
            QMessageBox.warning(self.dialog, "No Samples",
                                "No samples have been added.")
            return
        output_dir = QFileDialog.getExistingDirectory(
            self.dialog, "Select Output Directory",
            QgsProject.instance().homePath()
        )
        if not output_dir:
            return
        filename, ok = QInputDialog.getText(
            self.dialog,
            "Save Shapefile",
            "Enter the filename (without extension):",
            text="Manual Samples"
        )
        if not ok or not filename.strip():
            return
        full_path = os.path.join(output_dir, filename)
        if not full_path.lower().endswith('.shp'):
            full_path += '.shp'
        self.save_to_shapefile(full_path)
        self.manual_editing_active = False
        self.dialog.pushButtonedition.setEnabled(True)
        self.dialog.pushButtonfinishedition.setEnabled(False)

    def finish_coordinates(self):
        # Saves the samples gathered by coordinate entry
        self.save_samples("Samples by coordinates")
        self.dialog.pushButtonfinishcoordinates_judgmental.setEnabled(False)

    def finish_sampling_by_file(self):
        # Saves the samples gathered from a file
        self.save_samples("Samples by file")
        self.dialog.pushButtonfinishcoordinatesfile_judgmental.setEnabled(False)

    def save_to_shapefile(self, full_path):
        # Writes the in-memory features to a shapefile on disk
        self.renumber_features()
        error = QgsVectorFileWriter.writeAsVectorFormat(
            self.temp_layer,
            full_path,
            'UTF-8',
            self.sampling_area.crs(),
            'ESRI Shapefile'
        )
        if error[0] != QgsVectorFileWriter.NoError:
            QMessageBox.critical(
                self.dialog, "Error", f"Failed to create shapefile: {error}")
            return
        new_layer = QgsVectorLayer(full_path, os.path.basename(full_path), "ogr")
        if new_layer.isValid():
            symbol_path = self.dialog.layer_module.selected_symbol_editable
            if symbol_path and os.path.exists(symbol_path):
                symbol = QgsSymbol.defaultSymbol(new_layer.geometryType())
                svg_symbol_layer = QgsSvgMarkerSymbolLayer(symbol_path)
                symbol.changeSymbolLayer(0, svg_symbol_layer)
                new_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            order_field_index = new_layer.fields().indexOf('Order')
            if order_field_index != -1:
                new_layer.dataProvider().deleteAttributes([order_field_index])
                new_layer.updateFields()
            QgsProject.instance().addMapLayer(new_layer)
            QgsProject.instance().removeMapLayer(self.temp_layer.id())
            self.temp_layer = None
            self.stop_sampling()
            QMessageBox.information(
                self.dialog, "Success", "Samples have been saved successfully.")

    def save_samples(self, default_name):
        # General method to save samples to shapefile, used by coordinate and file sampling
        if not self.temp_layer or self.temp_layer.featureCount() == 0:
            QMessageBox.warning(self.dialog, "No Samples",
                                "No samples have been added.")
            return
        output_dir = QFileDialog.getExistingDirectory(
            self.dialog, "Select Output Directory")
        if not output_dir:
            return
        filename, ok = QInputDialog.getText(
            self.dialog,
            "File Name",
            "Enter name for output shapefile:",
            text=default_name
        )
        if not ok or not filename.strip():
            return
        full_path = os.path.join(output_dir, filename)
        if not full_path.lower().endswith('.shp'):
            full_path += '.shp'
        self.save_to_shapefile(full_path)

    def initialize_sampling(self):
        # Prepares the sampling process, creating or re-initializing the temporary layer if needed
        print("Initializing sampling...")
        layer_name = self.dialog.comboBoxshpsampling.currentText().split(" [")[0]
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            QMessageBox.warning(
                self.dialog, "Error", "No shapefile has been loaded/selected as the sampling area.")
            return False
        self.sampling_area = layers[0]
        print(f"Sampling area layer: {self.sampling_area.name()}")
        self.exclusion_zones = []
        for i in range(self.dialog.listWidgetexclusion.count()):
            item = self.dialog.listWidgetexclusion.item(i)
            layer_id = item.data(Qt.UserRole)
            zone_layer = QgsProject.instance().mapLayer(layer_id)
            if zone_layer:
                self.exclusion_zones.append(zone_layer)
        if not self.is_temp_layer_valid():
            self.create_temporary_layer()
            self.sample_count = 0
            self.sample_order.clear()
            self.coordinates_list.clear()
            print("Temporary layer created")
        if self.sampling_method == 'file':
            self.dialog.pushButtonloadfilejudgmental.setEnabled(True)
            self.dialog.pushButtonaddcoordinatesfile_judgmental.setEnabled(True)
            self.dialog.comboBoxcolumnx.setEnabled(True)
            self.dialog.comboBoxcolumny.setEnabled(True)
        elif self.sampling_method == 'coordinates':
            self.dialog.pushButtonfinishcoordinates_judgmental.setEnabled(True)
        elif self.sampling_method == 'manual':
            self.dialog.pushButtonfinishedition.setEnabled(True)
            self.dialog.pushButtonedition.setEnabled(False)
        return True

    def update_coordinates_list(self):
        # Updates the list widget with newly added coordinates in coordinate sampling mode
        if self.sampling_method != 'coordinates':
            return
        self.dialog.listWidgetlistofcoordinates_judgmental.clear()
        features = sorted(self.temp_layer.getFeatures(),
                          key=lambda f: f['Order'])
        for i, feature in enumerate(features, 1):
            point = feature.geometry().asPoint()
            self.dialog.listWidgetlistofcoordinates_judgmental.addItem(
                f"{i}) {point.x()}, {point.y()}"
            )

    def add_coordinates(self, point=None):
        # Adds a coordinate to the temporary layer, either from user input or map clicks
        try:
            if not self.is_temp_layer_valid():
                if not self.initialize_sampling():
                    return
                self.dialog.pushButtonedition.setEnabled(False)
                self.dialog.pushButtonfinishedition.setEnabled(True)
            try:
                if isinstance(point, QgsPointXY):
                    input_point = point
                elif point is None:
                    try:
                        x_text = self.dialog.lineEditxcoordinates_judgmental.text().strip()
                        y_text = self.dialog.lineEditycoordinate_judgmental.text().strip()
                        if not x_text or not y_text:
                            QMessageBox.warning(
                                self.dialog, "Input Error", "Please enter both X and Y coordinates.")
                            return
                        x = float(x_text)
                        y = float(y_text)
                        input_point = QgsPointXY(x, y)
                    except ValueError:
                        QMessageBox.warning(
                            self.dialog, "Input Error", "Coordinates must be numeric.")
                        return
                else:
                    print(f"Unexpected point type: {type(point)}")
                    QMessageBox.warning(
                        self.dialog, "Error", "Invalid point format.")
                    return
                if not self.allow_outside_sampling and not self.is_point_within_sampling_area(input_point):
                    QMessageBox.warning(
                        self.dialog, "Invalid Location", "The sample point is outside the sampling area.")
                    return
                if self.is_point_in_exclusion_zones(input_point):
                    QMessageBox.warning(
                        self.dialog, "Invalid Location", "The sample point is within an exclusion zone.")
                    return
                self.sample_count += 1
                feature = QgsFeature(self.temp_layer.fields())
                feature.setGeometry(QgsGeometry.fromPointXY(input_point))
                feature.setAttributes([
                    self.sample_count,
                    f"{self.dialog.lineEditsamplelabel.text().strip()}{self.sample_count}",
                    input_point.x(),
                    input_point.y(),
                    self.sample_count
                ])
                success = self.temp_layer.dataProvider().addFeatures([feature])
                if not success:
                    print("Failed to add feature to layer")
                    return
                self.sample_order.append(self.sample_count)
                if self.sampling_method == 'coordinates':
                    self.update_coordinates_list()
                self.temp_layer.triggerRepaint()
                self.canvas.refresh()
                if point is None and self.sampling_method == 'coordinates':
                    self.dialog.lineEditxcoordinates_judgmental.clear()
                    self.dialog.lineEditycoordinate_judgmental.clear()
            except Exception as e:
                print(f"Error adding coordinates: {str(e)}")
                QMessageBox.warning(
                    self.dialog, "Error", f"Failed to add coordinates: {str(e)}")
        except Exception as e:
            print(f"Error adding coordinates: {str(e)}")
            QMessageBox.warning(
                self.dialog, "Error", f"Failed to add coordinates: {str(e)}")

    def load_file(self):
        # Loads a CSV or XLSX file so that coordinates can be extracted and added to the map
        file_path, _ = QFileDialog.getOpenFileName(
            self.dialog, "Select CSV or XLSX File", "", "CSV Files (*.csv);;Excel Files (*.xlsx)")
        if not file_path:
            return
        self.dialog.lineEditaddsamplesbyfile.setText(file_path)
        try:
            if file_path.lower().endswith('.csv'):
                encodings = ['utf-8', 'latin1', 'iso-8859-1']
                delimiters = [',', ';', '\t']
                for encoding in encodings:
                    for delimiter in delimiters:
                        try:
                            self.file_data = pd.read_csv(file_path, encoding=encoding,
                                                         sep=delimiter, decimal='.')
                            if not self.file_data.empty:
                                break
                        except:
                            continue
                    if not self.file_data.empty:
                        break
                if self.file_data is None or self.file_data.empty:
                    QMessageBox.warning(
                        self.dialog,
                        "File Error",
                        "Could not read CSV file. Please check the file format and encoding.")
                    return
            elif file_path.lower().endswith('.xlsx'):
                self.file_data = pd.read_excel(file_path)
            else:
                QMessageBox.warning(
                    self.dialog, "File Error", "Unsupported file format.")
                return
            self.file_data.columns = self.file_data.columns.str.strip()
            columns = list(self.file_data.columns)
            self.dialog.comboBoxcolumnx.clear()
            self.dialog.comboBoxcolumny.clear()
            self.dialog.comboBoxcolumnx.addItems(columns)
            self.dialog.comboBoxcolumny.addItems(columns)
        except Exception as e:
            QMessageBox.warning(
                self.dialog, "File Error",
                f"Failed to read file: {str(e)}\nPlease check the file format and try again.")
            self.file_data = None

    def add_coordinates_from_file(self):
        # Adds coordinates from the loaded CSV/XLSX file to the temporary layer, handling invalid points
        try:
            if not self.is_temp_layer_valid():
                if not self.initialize_sampling():
                    return
                self.dialog.pushButtonedition.setEnabled(False)
                self.dialog.pushButtonfinishcoordinatesfile_judgmental.setEnabled(True)

            if self.file_data is None:
                QMessageBox.warning(
                    self.dialog, "Data Error", "No file data loaded.")
                return

            x_column = self.dialog.comboBoxcolumnx.currentText()
            y_column = self.dialog.comboBoxcolumny.currentText()
            if not x_column or not y_column:
                QMessageBox.warning(
                    self.dialog, "Selection Error", "Please select X and Y columns.")
                return
            invalid_points = []
            all_points = []
            for idx, row in self.file_data.iterrows():
                try:
                    x_str = str(row[x_column]).replace(',', '.')
                    y_str = str(row[y_column]).replace(',', '.')
                    x = float(x_str)
                    y = float(y_str)
                    input_point = QgsPointXY(x, y)
                    all_points.append((x, y, input_point))
                except ValueError:
                    invalid_points.append(
                        (row[x_column], row[y_column], "invalid coordinates"))
                except Exception as e:
                    invalid_points.append(
                        (row[x_column], row[y_column], f"error: {str(e)}"))
            if not all_points and not invalid_points:
                QMessageBox.warning(
                    self.dialog, "No Data", "No points found in the file.")
                return
            valid_points = []
            invalid_details = []
            for x, y, point in all_points:
                if not self.allow_outside_sampling and not self.is_point_within_sampling_area(point):
                    invalid_details.append((x, y, "outside sampling area"))
                    continue
                if self.is_point_in_exclusion_zones(point):
                    invalid_details.append((x, y, "within exclusion zone"))
                    continue
                valid_points.append((x, y, point))
            if invalid_details:
                msg = QMessageBox(self.dialog)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Invalid Points Detected")
                msg.setText("Some points are either outside the sampling area or within exclusion zones.")
                detailed_message = "The following points are invalid:\n"
                for x, y, reason in invalid_details:
                    detailed_message += f"X: {x}, Y: {y} - {reason}\n"
                msg.setInformativeText(detailed_message + "\nChoose how to proceed:")
                add_all_btn = msg.addButton("Add All Points", QMessageBox.AcceptRole)
                add_valid_btn = msg.addButton("Add Valid Points Only", QMessageBox.AcceptRole)
                cancel_btn = msg.addButton("Cancel", QMessageBox.RejectRole)
                msg.setStandardButtons(QMessageBox.NoButton)
                msg.exec_()
                clicked_button = msg.clickedButton()
                if clicked_button == add_all_btn:
                    reply = "add_all"
                elif clicked_button == add_valid_btn:
                    reply = "add_valid"
                else:
                    reply = "cancel"
            else:
                reply = "add_all"
            if reply == "cancel":
                return
            points_to_add = []
            if reply == "add_all":
                for x, y, point in all_points:
                    self.sample_count += 1
                    feature = QgsFeature(self.temp_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(point))
                    feature.setAttributes([
                        self.sample_count,
                        f"{self.dialog.lineEditsamplelabel.text().strip()}{self.sample_count}",
                        x,
                        y,
                        self.sample_count
                    ])
                    points_to_add.append(feature)
                    self.sample_order.append(self.sample_count)
            elif reply == "add_valid":
                for x, y, point in valid_points:
                    self.sample_count += 1
                    feature = QgsFeature(self.temp_layer.fields())
                    feature.setGeometry(QgsGeometry.fromPointXY(point))
                    feature.setAttributes([
                        self.sample_count,
                        f"{self.dialog.lineEditsamplelabel.text().strip()}{self.sample_count}",
                        x,
                        y,
                        self.sample_count
                    ])
                    points_to_add.append(feature)
                    self.sample_order.append(self.sample_count)
            if points_to_add:
                success = self.temp_layer.dataProvider().addFeatures(points_to_add)
                if not success:
                    QMessageBox.warning(
                        self.dialog, "Error", "Failed to add features to the layer.")
                    return
                self.temp_layer.triggerRepaint()
                self.canvas.refresh()
                if reply == "add_valid" and invalid_details:
                    message = "Some points were added successfully, but the following points were invalid:\n"
                    for x, y, reason in invalid_details:
                        message += f"X: {x}, Y: {y} - {reason}\n"
                    QMessageBox.warning(self.dialog, "Partial Success", message)
                elif reply == "add_all" and invalid_details:
                    message = "All points have been added. Note that some points may be outside the sampling area or within exclusion zones:\n"
                    for x, y, reason in invalid_details:
                        message += f"X: {x}, Y: {y} - {reason}\n"
                    QMessageBox.information(self.dialog, "All Points Added", message)
            else:
                QMessageBox.information(self.dialog, "No Points Added", "No valid points were found to add.")
        except Exception as e:
            print(f"Error in add_coordinates_from_file: {str(e)}")
            QMessageBox.warning(
                self.dialog, "Error", f"Failed to add coordinates from file: {str(e)}")

    def remove_coordinate(self, item):
        # Removes a coordinate from the temporary layer when a list item is double-clicked
        try:
            text = item.text()
            index = int(text.split(')')[0])
            request = QgsFeatureRequest().setFilterExpression(f'"Order" = {index}')
            feature_ids = [f.id() for f in self.temp_layer.getFeatures(request)]
            if feature_ids:
                self.temp_layer.dataProvider().deleteFeatures(feature_ids)
                if index in self.sample_order:
                    self.sample_order.remove(index)
                self.update_coordinates_list()
                self.temp_layer.triggerRepaint()
                self.canvas.refresh()
        except Exception as e:
            print(f"Error removing coordinate: {str(e)}")
            QMessageBox.warning(
                self.dialog, "Error", "Failed to remove the selected coordinate.")

    def remove_point_by_coordinates(self, point):
        # Removes a point from the temporary layer if the user right-clicks near it on the map
        if not self.is_temp_layer_valid():
            return
        if not isinstance(point, QgsPointXY):
            return
        tolerance = self.canvas.mapUnitsPerPixel() * 10
        closest_feature = None
        min_distance = float('inf')
        for feature in self.temp_layer.getFeatures():
            feature_point = feature.geometry().asPoint()
            distance = point.distance(feature_point)
            if distance < min_distance:
                min_distance = distance
                closest_feature = feature
        if closest_feature and min_distance < tolerance:
            self.temp_layer.dataProvider().deleteFeatures([closest_feature.id()])
            if closest_feature['Order'] in self.sample_order:
                self.sample_order.remove(closest_feature['Order'])
            if self.sampling_method == 'coordinates':
                self.update_coordinates_list()
            self.temp_layer.triggerRepaint()
            self.canvas.refresh()

    def create_temporary_layer(self):
        # Creates an in-memory temporary layer for storing user-added sample points
        crs = self.sampling_area.crs()
        if self.sampling_method == 'coordinates':
            layer_name = "Samples by Coordinates"
        elif self.sampling_method == 'manual':
            layer_name = "Temporary Manual Samples"
        elif self.sampling_method == 'file':
            layer_name = "Samples by File"
        else:
            layer_name = "Temporary Samples"
        self.temp_layer = QgsVectorLayer(
            f"Point?crs={crs.authid()}", layer_name, "memory")
        provider = self.temp_layer.dataProvider()
        provider.addAttributes([
            QgsField("ID", QVariant.Int),
            QgsField("Samples", QVariant.String),
            QgsField("X_coordinates", QVariant.Double),
            QgsField("Y_coordinates", QVariant.Double),
            QgsField("Order", QVariant.Int)
        ])
        self.temp_layer.updateFields()
        symbol = QgsSymbol.defaultSymbol(self.temp_layer.geometryType())
        symbol.setColor(Qt.cyan)
        self.temp_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        QgsProject.instance().addMapLayer(self.temp_layer)

    def is_point_within_sampling_area(self, point):
        # Checks if a given point is inside the sampling area's geometry
        point_geom = QgsGeometry.fromPointXY(point)
        for feature in self.sampling_area.getFeatures():
            if feature.geometry().contains(point_geom):
                return True
        return False

    def is_point_in_exclusion_zones(self, point):
        # Checks if a given point is inside any of the exclusion zone layers
        point_geom = QgsGeometry.fromPointXY(point)
        for zone in self.exclusion_zones:
            for feature in zone.getFeatures():
                if feature.geometry().contains(point_geom):
                    return True
        return False

    def renumber_features(self):
        # Renumbers the features so that their order starts at 1 and increments sequentially
        features = sorted(self.temp_layer.getFeatures(),
                          key=lambda f: f['Order'])
        updates = {}
        label_root = self.dialog.lineEditsamplelabel.text().strip()
        for new_id, feature in enumerate(features, 1):
            updates[feature.id()] = {
                self.temp_layer.fields().indexOf('ID'): new_id,
                self.temp_layer.fields().indexOf('Samples'): f"{label_root}{new_id}",
                self.temp_layer.fields().indexOf('Order'): new_id
            }
        self.temp_layer.dataProvider().changeAttributeValues(updates)

    def handle_layer_removed(self, layer_id):
        # Handles cleanup when a layer is removed from the QGIS project
        try:
            if self.temp_layer and self.temp_layer.id() == layer_id:
                self.temp_layer = None
                self.dialog.pushButtonedition.setEnabled(True)
                self.dialog.pushButtonfinishedition.setEnabled(False)
        except RuntimeError:
            self.temp_layer = None


class SamplingMapTool(QgsMapTool):
    # This custom map tool handles clicks on the map to add or remove sample points
    def __init__(self, canvas, sampling):
        super().__init__(canvas)
        self.sampling = sampling
        self.canvas = canvas

    def canvasReleaseEvent(self, event):
        # Detects left or right clicks and adds or removes points accordingly
        if event.button() == Qt.LeftButton:
            point = self.toMapCoordinates(event.pos())
            if isinstance(point, QgsPointXY):
                self.sampling.add_coordinates(point)
            else:
                print(f"Invalid point type from canvas: {type(point)}")
        elif event.button() == Qt.RightButton:
            point = self.toMapCoordinates(event.pos())
            if isinstance(point, QgsPointXY):
                self.sampling.remove_point_by_coordinates(point)
            else:
                print(f"Invalid point type from canvas: {type(point)}")

    def isZoomTool(self):
        # Indicates this map tool is not a zoom tool
        return False

    def isTransient(self):
        # Indicates this map tool does not reset on mouse move
        return False

    def isEditTool(self):
        # Indicates this map tool is used for editing
        return True
