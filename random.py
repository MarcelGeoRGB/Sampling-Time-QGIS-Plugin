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

import os
import random
from qgis.core import (
    QgsGeometry, QgsFeature, QgsPointXY, QgsVectorLayer, QgsField,
    QgsProject, QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsVectorFileWriter,
    QgsWkbTypes, QgsSvgMarkerSymbolLayer, QgsFeatureRequest
)
from qgis.PyQt.QtCore import QVariant, Qt, QCoreApplication, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QMessageBox, QApplication, QFileDialog, QInputDialog, QLineEdit, QProgressDialog
)
from qgis.gui import QgsMapTool

class SamplingWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, list, int)
    warning = pyqtSignal(str, str)

    def __init__(self, sampling_obj):
        super().__init__()
        self.sampling_obj = sampling_obj
        self.is_cancelled = False
        self.samples = []
        self.current_samples = []

    def run(self):
        # This method handles the main sampling loop for random point generation
        try:
            extent = self.sampling_obj.sampling_area.extent()
            attempts = 0
            max_attempts = 5000
            samples_generated = 0

            # Keep trying until desired samples or max attempts are reached
            while len(self.current_samples) < self.sampling_obj.num_samples and attempts < max_attempts:
                if self.is_cancelled:
                    # If user cancels, trigger the finished signal with no valid output
                    self.finished.emit(False, [], attempts)
                    return

                # Generate random point within the sampling area's extent
                x = random.uniform(extent.xMinimum(), extent.xMaximum())
                y = random.uniform(extent.yMinimum(), extent.yMaximum())
                point = QgsPointXY(x, y)
                point_geom = QgsGeometry.fromPointXY(point)

                # Ensure the point is actually within the sampling area polygon
                if not any(f.geometry().contains(point_geom) for f in self.sampling_obj.sampling_area.getFeatures()):
                    attempts += 1
                    continue

                # Verify distance constraints if set
                is_valid = True
                if self.sampling_obj.min_distance_samples > 0:
                    for existing_point in self.current_samples:
                        if point.distance(existing_point) < self.sampling_obj.min_distance_samples:
                            is_valid = False
                            break

                # If valid, confirm additional checks and add point to current_samples
                if is_valid and self.sampling_obj.is_valid_sample(point, show_warning=False, is_random=True):
                    self.current_samples.append(point)
                    samples_generated += 1
                    self.progress.emit(samples_generated)

                attempts += 1

            # If not enough samples could be created, show a warning
            if len(self.current_samples) < self.sampling_obj.num_samples:
                warning_text = (
                    f"Could not generate all requested samples.\n"
                    f"Requested samples: {self.sampling_obj.num_samples}\n"
                    f"Generated samples: {len(self.current_samples)}\n"
                    f"Attempts made: {attempts}\n"
                    f"This might be due to:\n"
                    f"- Distance constraints being too strict\n"
                    f"- Sampling area being too small\n"
                    f"- Too many samples requested for the available space\n"
                    f"Try adjusting these parameters and try again."
                )
                self.warning.emit("Warning", warning_text)

            # Emit signal with final status, generated points, and attempts
            self.finished.emit(True, self.current_samples, attempts)

        except Exception:
            # If an error occurs, finish with an error state
            self.finished.emit(False, [], 0)

    def stop(self):
        # Sets a flag to cancel the ongoing sampling
        self.is_cancelled = True

class RandomSampling:
    def __init__(self, iface, ui):
        # Initialize variables and UI elements for random sampling
        self.iface = iface
        self.ui = ui
        self.sampling_area = None
        self.exclusion_zones = []
        self.num_samples = 0
        self.min_distance_perimeter = 0
        self.min_distance_samples = 0
        self.min_distance_exclusion = 0
        self.samples = []
        self.temp_layer = None
        self.label_root = ""
        self.selected_symbol = None
        self.selected_symbol_editable = None
        self.map_tool = None
        self.allow_outside_sampling = False
        self.instructions_shown = False
        self.worker = None
        self.progress_dialog = None
        self.layer_removed_connection = None

        # Disable controls at initialization
        self.disable_controls()
        self.ui.checkBoxaddsamplesrandomly.stateChanged.connect(
            self.on_checkBoxaddsamplesrandomly_stateChanged
        )
        self.ui.checkBoxoutsidesamplingrandom.stateChanged.connect(
            self.on_checkBoxoutsidesamplingrandom_stateChanged
        )
        
    def disable_controls(self):
        # Disable random sampling UI controls
        controls = [
            self.ui.pushButtonrandomstart,
            self.ui.pushButtonrandomreset,
            self.ui.pushButtonrandomsave,
            self.ui.spinBoxnumberofsamples,
            self.ui.doubleSpinBoxdistanceperimeter,
            self.ui.doubleSpinBoxdistancesamples,
            self.ui.doubleSpinBoxdistanceexclusion,
            self.ui.checkBoxoutsidesamplingrandom
        ]
        for control in controls:
            control.setEnabled(False)

    def enable_controls(self):
        # Enable random sampling UI controls
        controls = [
            self.ui.pushButtonrandomstart,
            self.ui.pushButtonrandomreset,
            self.ui.pushButtonrandomsave,
            self.ui.spinBoxnumberofsamples,
            self.ui.doubleSpinBoxdistanceperimeter,
            self.ui.doubleSpinBoxdistancesamples,
            self.ui.doubleSpinBoxdistanceexclusion,
            self.ui.checkBoxoutsidesamplingrandom
        ]
        for control in controls:
            control.setEnabled(True)

    def on_checkBoxaddsamplesrandomly_stateChanged(self, state):
        # Triggered when random sampling checkbox is checked/unchecked
        if state == Qt.Checked:
            self.enable_controls()
            # Show instructions only once
            if not self.instructions_shown:
                QMessageBox.information(
                    self.ui,
                    "Instructions",
                    "Required settings:\n"
                    "- Enter the required number of random samples\n\n"
                    "Optional settings:\n"
                    "- Set minimum distance between samples\n"
                    "- Set minimum distance between samples and the perimeter\n"
                    "- Set minimum distance between samples and exclusion zones\n"
                    "- 'Allow Outside Sampling': enables manual sampling outside the perimeter\n\n"
                    "Workflow:\n"
                    "1. Click 'Start' to generate random samples\n"
                    "2. Use 'Reset' for a new set\n"
                    "3. Left click to add samples manually\n"
                    "4. Right click to remove samples\n"
                    "5. Click 'Save' to create the final shapefile"
                )
                self.instructions_shown = True
        else:
            self.disable_controls()
            self.instructions_shown = False

    def on_checkBoxoutsidesamplingrandom_stateChanged(self, state):
        # Toggle manual sampling outside the perimeter
        self.allow_outside_sampling = state == Qt.Checked

    def set_parameters(self, num_samples, min_distance_perimeter, min_distance_samples, min_distance_exclusion, label_root, allow_outside_sampling=False):
        # Manually set parameters for random sampling
        self.num_samples = num_samples
        self.min_distance_perimeter = min_distance_perimeter
        self.min_distance_samples = min_distance_samples
        self.min_distance_exclusion = min_distance_exclusion
        self.label_root = label_root
        self.allow_outside_sampling = allow_outside_sampling

    def update_parameters(self):
        # Update parameters from UI elements
        try:
            self.num_samples = self.ui.spinBoxnumberofsamples.value()
            self.min_distance_perimeter = self.ui.doubleSpinBoxdistanceperimeter.value()
            self.min_distance_samples = self.ui.doubleSpinBoxdistancesamples.value()
            self.min_distance_exclusion = self.ui.doubleSpinBoxdistanceexclusion.value()
            self.allow_outside_sampling = self.ui.checkBoxoutsidesamplingrandom.isChecked()
            print(f"Updated min_distance_samples: {self.min_distance_samples}")
        except Exception as e:
            print(f"Error updating parameters: {str(e)}")

    def set_symbol(self, symbol, symbol_editable):
        # Assign chosen symbol style for samples
        self.selected_symbol = symbol
        self.selected_symbol_editable = symbol_editable

    def set_sampling_area(self, layer):
        # Define the layer used as sampling area
        self.sampling_area = layer

    def set_exclusion_zones(self, exclusion_layers):
        # Set exclusion zones (layers) that cannot contain points
        self.exclusion_zones = exclusion_layers

    def show_warning(self, title, message):
        # Convenient method to show a warning dialog
        QMessageBox.warning(self.ui, title, message)

    def handle_worker_finished(self, success, samples, attempts):
        # Callback for when the worker finishes random sampling
        if success:
            self.samples = samples
            # If samples exist, create a temporary layer to visualize them
            if self.samples:
                self.create_temp_layer()
            # If fewer samples than requested, no further action needed here
            if len(self.samples) < self.num_samples:
                pass
            else:
                QMessageBox.information(self.ui, "Success", f"{len(samples)} samples have been generated.")
        else:
            self.reset()
        self.progress_dialog.close()
        self.progress_dialog.deleteLater()
        self.progress_dialog = None

    def on_pushButtonrandomstart_clicked(self):
        # Starts the generation of random samples
        try:
            # If there's already a temp layer with samples, prompt user
            if self.temp_layer is not None and not self.temp_layer.isValid():
                self.temp_layer = None
                self.samples = []

            if self.samples:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")
                return

            if self.ui.spinBoxnumberofsamples.value() <= 0:
                QMessageBox.warning(self.ui, "Error", "Please specify the number of samples.")
                return

            self.update_parameters()
            layer_name = self.ui.comboBoxshpsampling.currentText().split(" [")[0]
            layers = QgsProject.instance().mapLayersByName(layer_name)
            
            if not layers:
                QMessageBox.warning(self.ui, "Error", "Sampling layer not found.")
                return
                
            self.set_sampling_area(layers[0])
            exclusion_layers = []
            
            # Collect all exclusion zone layers from the list widget
            for i in range(self.ui.listWidgetexclusion.count()):
                item = self.ui.listWidgetexclusion.item(i)
                layer_id = item.data(Qt.UserRole)
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    exclusion_layers.append(layer)
                    
            self.set_exclusion_zones(exclusion_layers)
            self.label_root = self.ui.lineEditsamplelabel.text().strip()
            
            # Retrieve the chosen symbol from the combobox
            index = self.ui.comboBoxsymbol.currentIndex()
            if index >= 0:
                symbol_data = self.ui.comboBoxsymbol.itemData(index)
                if symbol_data:
                    self.selected_symbol, self.selected_symbol_editable = symbol_data

            result = self.generate_samples()
            if result is None:
                return

            samples, attempts = result

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error starting sampling: {str(e)}")

    def generate_samples(self):
        # Creates a thread (SamplingWorker) to handle random sampling
        try:
            if not self.sampling_area:
                QMessageBox.warning(self.ui, "Error", "No sampling area defined.")
                return None

            if self.temp_layer is not None:
                QMessageBox.information(self.ui, "Info", "Samples already exist. Use 'Reset' button to generate a new set.")
                return None

            self.samples = []
            
            # Create a progress dialog to show the sampling progress
            self.progress_dialog = QProgressDialog("Generating random samples...", "Cancel", 0, self.num_samples, self.ui)
            self.progress_dialog.setWindowTitle("Progress")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setMinimumDuration(0)

            # Create and configure the worker
            self.worker = SamplingWorker(self)
            self.worker.progress.connect(self.progress_dialog.setValue)
            self.worker.finished.connect(self.handle_worker_finished)
            self.worker.warning.connect(self.show_warning)
            self.progress_dialog.canceled.connect(self.worker.stop)

            # Start sampling in a separate thread
            self.worker.start()
            result = self.progress_dialog.exec_()
            if result == QProgressDialog.Rejected:
                self.worker.stop()
            return (self.samples, len(self.samples))

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error generating samples: {str(e)}")
            return None

    def on_pushButtonrandomreset_clicked(self):
        # Resets the current sampling process and starts a new one
        try:
            if self.temp_layer is not None and not self.temp_layer.isValid():
                self.temp_layer = None
                self.samples = []

            self.update_parameters()
            
            layer_name = self.ui.comboBoxshpsampling.currentText().split(" [")[0]
            layers = QgsProject.instance().mapLayersByName(layer_name)
            
            if not layers:
                QMessageBox.warning(self.ui, "Error", "Sampling layer not found.")
                return
                    
            self.set_sampling_area(layers[0])
            
            exclusion_layers = []
            for i in range(self.ui.listWidgetexclusion.count()):
                item = self.ui.listWidgetexclusion.item(i)
                layer_id = item.data(Qt.UserRole)
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    exclusion_layers.append(layer)
                        
            self.set_exclusion_zones(exclusion_layers)
            
            self.label_root = self.ui.lineEditsamplelabel.text().strip()
            index = self.ui.comboBoxsymbol.currentIndex()
            if index >= 0:
                symbol_data = self.ui.comboBoxsymbol.itemData(index)
                if symbol_data:
                    self.selected_symbol, self.selected_symbol_editable = symbol_data

            self.reset()
            result = self.generate_samples()
            if result is not None:
                samples, attempts = result

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error resetting samples: {str(e)}")

    def on_pushButtonrandomsave_clicked(self):
        # Saves the generated samples to a shapefile
        if not self.samples:
            QMessageBox.warning(self.ui, "Error", "No samples to save. Please generate samples first.")
            return

        output_dir = QFileDialog.getExistingDirectory(
            self.ui, "Select Output Directory", 
            QgsProject.instance().homePath()
        )
        if not output_dir:
            return

        filename, ok = QInputDialog.getText(
            self.ui, "Save Shapefile",
            "Enter filename (without extension):",
            QLineEdit.Normal, "random_samples"
        )
        if not ok or not filename:
            return

        if self.save_samples(output_dir, filename):
            QMessageBox.information(
                self.ui, "Success",
                "Samples have been saved successfully."
            )

    def save_samples(self, output_dir, filename):
        # Writes the temporary layer to disk as a shapefile and adds it to the project
        try:
            if not self.temp_layer or not self.samples:
                return False

            self.renumber_samples()
            output_path = os.path.join(output_dir, f"{filename}.shp")

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "ESRI Shapefile"
            options.fileEncoding = "UTF-8"

            error = QgsVectorFileWriter.writeAsVectorFormat(
                self.temp_layer, output_path, options
            )

            if error[0] == QgsVectorFileWriter.NoError:
                new_layer = QgsVectorLayer(output_path, filename, "ogr")
                if new_layer.isValid():
                    QgsProject.instance().addMapLayer(new_layer)

                    # Apply selected symbol if available
                    if self.selected_symbol_editable:
                        symbol = QgsMarkerSymbol.createSimple({'name': 'circle'})
                        svg_symbol = QgsSvgMarkerSymbolLayer(self.selected_symbol_editable)
                        symbol.changeSymbolLayer(0, svg_symbol)
                    else:
                        symbol = QgsMarkerSymbol.createSimple({
                            'name': 'circle',
                            'color': '0,255,255'
                        })

                    new_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
                    QgsProject.instance().removeMapLayer(self.temp_layer)
                    self.temp_layer = None
                    
                    if self.map_tool:
                        self.iface.mapCanvas().unsetMapTool(self.map_tool)
                        self.map_tool = None
                    self.iface.actionPan().trigger()
                    
                    return True

            return False
                
        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error saving samples: {str(e)}")
            return False

    def reset(self):
        # Removes any temporary layer and stops the current worker if active
        if self.temp_layer:
            if QgsProject.instance().mapLayer(self.temp_layer.id()):
                QgsProject.instance().removeMapLayer(self.temp_layer)
            if self.layer_removed_connection:
                QgsProject.instance().layerWillBeRemoved.disconnect(self.on_layer_removed)
                self.layer_removed_connection = None
        self.samples = []
        self.temp_layer = None
        if self.worker:
            self.worker.stop()
            self.worker = None

    def is_valid_sample(self, point, show_warning=True, is_manual=False, is_random=False):
        # Checks if a potential point satisfies all constraints (area, distances, etc.)
        point_geom = QgsGeometry.fromPointXY(point)
        print(f"Checking sample with min_distance_samples: {self.min_distance_samples}")

        # If user is manually placing a point and outside-sampling is not allowed, ensure it's inside the area
        if is_manual:
            if not self.allow_outside_sampling:
                if not any(f.geometry().contains(point_geom) for f in self.sampling_area.getFeatures()):
                    if show_warning:
                        QMessageBox.warning(self.ui, "Invalid Location", 
                                          "Point is outside sampling area.")
                    return False
        elif is_random:
            # Random point must be inside the area to be valid
            if not any(f.geometry().contains(point_geom) for f in self.sampling_area.getFeatures()):
                return False

        # Check if the point lies in an exclusion zone or too close to it
        if self.exclusion_zones:
            for zone in self.exclusion_zones:
                for feature in zone.getFeatures():
                    # If point is inside an exclusion zone, reject it
                    if feature.geometry().contains(point_geom):
                        if show_warning:
                            QMessageBox.warning(self.ui, "Invalid Location", 
                                             "Point is in exclusion zone.")
                        return False
                    
                    # If there's a minimum distance from exclusion zones, check that too
                    if self.min_distance_exclusion > 0:
                        if feature.geometry().distance(point_geom) < self.min_distance_exclusion:
                            if show_warning:
                                QMessageBox.warning(self.ui, "Invalid Location", 
                                                 f"Point too close to exclusion zone (min: {self.min_distance_exclusion}m)")
                            return False

        # Check if point is too close to the perimeter of the sampling area
        if self.min_distance_perimeter > 0:
            for feature in self.sampling_area.getFeatures():
                if feature.geometry().contains(point_geom):
                    if self.calculate_distance_to_boundary(feature.geometry(), point_geom) < self.min_distance_perimeter:
                        if show_warning:
                            QMessageBox.warning(self.ui, "Invalid Location", 
                                             f"Point too close to perimeter (min: {self.min_distance_perimeter}m)")
                        return False
                    break

        # Check if point is too close to an existing sample
        if self.min_distance_samples > 0 and self.samples:
            for existing_point in self.samples:
                distance = point.distance(existing_point)
                if distance < self.min_distance_samples:
                    if show_warning:
                        QMessageBox.warning(self.ui, "Invalid Location", 
                                         f"Point too close to another sample (min: {self.min_distance_samples}m)")
                    print(f"Sample rejected - too close: {distance} < {self.min_distance_samples}")
                    return False
            print(f"Sample accepted - min distance check passed")

        return True

    def calculate_distance_to_boundary(self, geometry, point_geom):
        # Calculates the shortest distance from a point to the boundary of a polygon
        if geometry.type() == QgsWkbTypes.PolygonGeometry:
            if geometry.isMultipart():
                distances = [
                    QgsGeometry.fromPolylineXY(ring).distance(point_geom)
                    for polygon in geometry.asMultiPolygon()
                    for ring in polygon
                ]
                return min(distances) if distances else float('inf')
            else:
                return min(
                    QgsGeometry.fromPolylineXY(ring).distance(point_geom)
                    for ring in geometry.asPolygon()
                )
        return geometry.distance(point_geom)

    def create_temp_layer(self):
        # Creates an in-memory layer to temporarily hold sampled points
        try:
            if self.temp_layer is not None:
                QgsProject.instance().removeMapLayer(self.temp_layer)
                self.temp_layer = None

            self.temp_layer = QgsVectorLayer(
                f"Point?crs={self.sampling_area.crs().authid()}",
                "Random Samples", "memory"
            )

            provider = self.temp_layer.dataProvider()
            provider.addAttributes([
                QgsField("ID", QVariant.Int),
                QgsField("Samples", QVariant.String),
                QgsField("X", QVariant.Double),
                QgsField("Y", QVariant.Double)
            ])
            self.temp_layer.updateFields()

            # Populate layer with sampled points
            features = []
            for i, point in enumerate(self.samples, 1):
                feature = QgsFeature(self.temp_layer.fields())
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                feature.setAttributes([
                    i, f"{self.label_root}{i}", point.x(), point.y()
                ])
                features.append(feature)

            provider.addFeatures(features)
            self.temp_layer.updateExtents()

            # Assign a basic symbol if none is specifically chosen
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': '0,255,255',
                'outline_color': '0,0,0',
                'outline_width': '0.2'
            })
            self.temp_layer.setRenderer(QgsSingleSymbolRenderer(symbol))

            QgsProject.instance().addMapLayer(self.temp_layer)

            # Track if layer is removed
            self.layer_removed_connection = QgsProject.instance().layerWillBeRemoved.connect(self.on_layer_removed)

            # Set custom map tool to allow adding/removing points by clicking
            self.map_tool = SamplingMapTool(self.iface.mapCanvas(), self)
            self.iface.mapCanvas().setMapTool(self.map_tool)

        except Exception as e:
            QMessageBox.critical(self.ui, "Error", f"Error creating temporary layer: {str(e)}")

    def on_layer_removed(self, layer_id):
        # If the temporary layer is removed manually, clear the reference
        if self.temp_layer and self.temp_layer.id() == layer_id:
            self.temp_layer = None

    def add_sample(self, point):
        # Allows user to manually add a sample point on left-click
        if self.temp_layer is None:
            self.create_temp_layer()

        if not self.allow_outside_sampling:
            self.allow_outside_sampling = self.ui.checkBoxoutsidesamplingrandom.isChecked()
            
        if not self.is_valid_sample(point, show_warning=True, is_manual=True):
            return

        self.samples.append(point)

        feature = QgsFeature(self.temp_layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature.setAttributes([
            len(self.samples),
            f"{self.label_root}{len(self.samples)}",
            point.x(),
            point.y()
        ])
        self.temp_layer.dataProvider().addFeatures([feature])
        self.temp_layer.updateExtents()
        self.renumber_samples()

    def remove_sample(self, point):
        # Allows user to manually remove the nearest sample point on right-click
        nearest_feature = None
        min_distance = float('inf')
        nearest_point = None

        for feature in self.temp_layer.getFeatures():
            distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
            if distance < min_distance:
                min_distance = distance
                nearest_feature = feature
                nearest_point = feature.geometry().asPoint()

        if nearest_feature:
            self.temp_layer.dataProvider().deleteFeatures([nearest_feature.id()])
            self.temp_layer.updateExtents()

            if nearest_point in self.samples:
                self.samples.remove(nearest_point)

            self.temp_layer.triggerRepaint()
            self.renumber_samples()

    def renumber_samples(self):
        # Updates attribute table IDs and labels after adding/removing points
        point_to_feature_id = {
            (feature.geometry().asPoint().x(), feature.geometry().asPoint().y()): feature.id()
            for feature in self.temp_layer.getFeatures()
        }

        updates = {}
        for i, point in enumerate(self.samples, 1):
            feature_id = point_to_feature_id.get((point.x(), point.y()))
            if feature_id is not None:
                updates[feature_id] = {
                    self.temp_layer.fields().lookupField('ID'): i,
                    self.temp_layer.fields().lookupField('Samples'): f"{self.label_root}{i}",
                    self.temp_layer.fields().lookupField('X'): point.x(),
                    self.temp_layer.fields().lookupField('Y'): point.y()
                }

        self.temp_layer.dataProvider().changeAttributeValues(updates)
        self.temp_layer.triggerRepaint()

class SamplingMapTool(QgsMapTool):
    def __init__(self, canvas, sampling):
        # Custom map tool to capture mouse clicks for adding/removing samples
        super().__init__(canvas)
        self.sampling = sampling

    def canvasReleaseEvent(self, event):
        # Left click adds a sample, right click removes the closest sample
        if event.button() == Qt.LeftButton:
            self.sampling.add_sample(self.toMapCoordinates(event.pos()))
        elif event.button() == Qt.RightButton:
            self.sampling.remove_sample(self.toMapCoordinates(event.pos()))
