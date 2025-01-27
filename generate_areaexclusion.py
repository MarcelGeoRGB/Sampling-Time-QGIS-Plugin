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

import os  # Handles file system operations
import math  # Provides mathematical functions
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog, QInputDialog
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsVectorFileWriter,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
    QgsFillSymbol,
    QgsSymbol,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.PyQt.QtGui import QColor


class AreaExclusionModule:
    """
    This class handles the creation of area-based sampling layers or coordinates-based sampling.
    It controls user interface elements, checks states, and saves shapefiles.
    """
    def __init__(self, iface, dialog):
        self.iface = iface  # Reference to QGIS interface
        self.dialog = dialog  # Reference to the plugin dialog
        self.canvas = iface.mapCanvas()  # Reference to the map canvas

        self.prev_sampling_checked = False  # Tracks previous state of sampling checkbox
        self.prev_coordinates_checked = False  # Tracks previous state of coordinates checkbox

        self.area_tool = None  # Will hold the area digitizing tool instance
        self.circle_tool = None  # Will hold the circle digitizing tool instance
        self.temp_sampling_layer = None  # Temporary layer for digitized sampling polygons
        self.temp_coordinates_layer = None  # Temporary layer for coordinate-based polygons
        self.temp_lines_rubber_band = None  # Rubber band for drawing lines between coordinates
        self.feature_id = 1  # Counter to track features
        self.coordinates = []  # List of coordinate points

        self.setup_ui_connections()  # Sets up signals/slots for UI

    def setup_ui_connections(self):
        """
        Connects UI elements (checkboxes, buttons, etc.) to their respective methods.
        """
        self.dialog.checkBoxshpsamplingarea.stateChanged.connect(self.toggle_buttons)
        self.dialog.checkBoxgenerateshpbycoordinates.stateChanged.connect(self.toggle_buttons)
        self.dialog.pushButtonareasampleshp.clicked.connect(self.start_area_digitizing)
        self.dialog.pushButtoncirclesampleshp.clicked.connect(self.start_circle_digitizing)
        self.dialog.pushButtonfinishareashp.clicked.connect(self.save_final_shapefile)
        self.dialog.pushButtonaddcoordinates.clicked.connect(self.add_coordinates)
        self.dialog.pushButtonfinishcoordinates.clicked.connect(self.finish_coordinates_digitizing)
        self.dialog.listWidgetlistofcoordinates.itemDoubleClicked.connect(self.remove_last_coordinate)
        self.toggle_buttons(Qt.Unchecked)

    def toggle_buttons(self, state):
        """
        Adjusts the available UI elements depending on which checkbox is checked.
        """
        sender = self.dialog.sender()
        if sender == self.dialog.checkBoxshpsamplingarea and self.dialog.checkBoxshpsamplingarea.isChecked():
            self.dialog.checkBoxgenerateshpbycoordinates.blockSignals(True)
            self.dialog.checkBoxgenerateshpbycoordinates.setChecked(False)
            self.dialog.checkBoxgenerateshpbycoordinates.blockSignals(False)
        elif sender == self.dialog.checkBoxgenerateshpbycoordinates and self.dialog.checkBoxgenerateshpbycoordinates.isChecked():
            self.dialog.checkBoxshpsamplingarea.blockSignals(True)
            self.dialog.checkBoxshpsamplingarea.setChecked(False)
            self.dialog.checkBoxshpsamplingarea.blockSignals(False)

        sampling_checked = self.dialog.checkBoxshpsamplingarea.isChecked()
        coordinates_checked = self.dialog.checkBoxgenerateshpbycoordinates.isChecked()

        self.dialog.lineEditEPSGcode.setEnabled(sampling_checked or coordinates_checked)
        self.dialog.pushButtonareasampleshp.setEnabled(sampling_checked)
        self.dialog.pushButtoncirclesampleshp.setEnabled(sampling_checked)
        self.dialog.pushButtonfinishareashp.setEnabled(sampling_checked)
        self.dialog.lineEditxcoordinates.setEnabled(coordinates_checked)
        self.dialog.lineEditycoordinate.setEnabled(coordinates_checked)
        self.dialog.pushButtonaddcoordinates.setEnabled(coordinates_checked)
        self.dialog.pushButtonfinishcoordinates.setEnabled(coordinates_checked)
        self.dialog.listWidgetlistofcoordinates.setEnabled(coordinates_checked)

        if sampling_checked and not self.prev_sampling_checked and not coordinates_checked:
            self.show_instructions_sampling()

        if coordinates_checked and not self.prev_coordinates_checked and not sampling_checked:
            self.show_instructions_coordinates()

        self.prev_sampling_checked = sampling_checked
        self.prev_coordinates_checked = coordinates_checked

    def show_instructions_sampling(self):
        """
        Displays instructions on how to digitize areas (polygons or circles).
        """
        msg = (
            "Tool Usage Instructions:\n\n"
            "Generate Sample Areas / Exclusion Zones:\n\n"
            "Area button: Create polygons using segments\n"
            "- Left click to add points\n"
            "- Right click to finish\n\n"
            "Circle button: Create circles using two points\n"
            "- Left click for center point\n"
            "- Right click to set radius\n\n"
            "For both tools:\n"
            "- Add ID when prompted\n"
            "- Click OK to save or Cancel to start new digitizing\n"
            "- Set EPSG code before finishing\n"
            "- Click Finish button to create final shapefile"
        )
        QMessageBox.information(None, "Generate Sample Areas / Exclusion Zones", msg)

    def show_instructions_coordinates(self):
        """
        Displays instructions on how to generate a polygon by manual coordinate input.
        """
        msg = (
            "Tool Usage Instructions:\n\n"
            "Generate by Coordinates:\n"
            "- Enter X coordinate in the X field\n"
            "- Enter Y coordinate in the Y field\n"
            "- Click 'Add Coordinates' to add the point to the list\n"
            "- Points will be displayed in real-time on the map\n"
            "- Ensure to add coordinates in order to define the area correctly\n"
            "- The last point will auto-connect to the first, closing the area.\n"
            "- Once all points are added, enter the EPSG code\n"
            "- Click 'Finish' to create the final shapefile\n\n"
        )
        QMessageBox.information(None, "Generate Sample Areas / Exclusion Zones", msg)

    def create_temp_sampling_layer(self):
        """
        Creates a temporary in-memory layer for digitizing polygons or circles if not already existing.
        """
        if not self.temp_sampling_layer:
            project_crs = QgsProject.instance().crs()
            self.temp_sampling_layer = QgsVectorLayer(
                f"Polygon?crs={project_crs.authid()}", "Temporary Sampling Areas", "memory"
            )
            provider = self.temp_sampling_layer.dataProvider()
            provider.addAttributes(
                [
                    QgsField("id", QVariant.String),
                    QgsField("type", QVariant.String),
                ]
            )
            self.temp_sampling_layer.updateFields()
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "255,0,0,100",
                    "outline_color": "255,0,0,255",
                    "outline_width": "0.8",
                }
            )
            self.temp_sampling_layer.renderer().setSymbol(symbol)
            QgsProject.instance().addMapLayer(self.temp_sampling_layer)
            self.feature_id = 1

    def create_temp_coordinates_layer(self):
        """
        Creates a temporary in-memory layer for coordinate-based polygons if not already existing,
        and a rubber band to connect points.
        """
        if not self.temp_coordinates_layer:
            project_crs = QgsProject.instance().crs()
            self.temp_coordinates_layer = QgsVectorLayer(
                f"Point?crs={project_crs.authid()}", "Temporary Coordinates", "memory"
            )
            provider = self.temp_coordinates_layer.dataProvider()
            provider.addAttributes(
                [
                    QgsField("id", QVariant.String),
                ]
            )
            self.temp_coordinates_layer.updateFields()
            symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PointGeometry)
            if symbol is None:
                symbol = QgsSymbol.createSimple({"name": "circle", "color": "0,0,255", "size": "3"})
            symbol.setColor(QColor(0, 0, 255))
            self.temp_coordinates_layer.renderer().setSymbol(symbol)
            QgsProject.instance().addMapLayer(self.temp_coordinates_layer)

        if not self.temp_lines_rubber_band:
            self.temp_lines_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.temp_lines_rubber_band.setColor(QColor(0, 255, 0))
            self.temp_lines_rubber_band.setWidth(2)

    def start_area_digitizing(self):
        """
        Activates the tool that allows drawing polygons (area) on the map.
        """
        self.create_temp_sampling_layer()
        self.area_tool = AreaDigitizingTool(self.iface, self)
        self.canvas.setMapTool(self.area_tool)
        self.dialog.showMinimized()

    def start_circle_digitizing(self):
        """
        Activates the tool that allows drawing circles on the map.
        """
        self.create_temp_sampling_layer()
        self.circle_tool = CircleDigitizingTool(self.iface, self)
        self.canvas.setMapTool(self.circle_tool)
        self.dialog.showMinimized()

    def add_coordinates(self):
        """
        Adds a manually inputted X,Y coordinate to the list and updates the temporary layer and lines.
        """
        x_text = self.dialog.lineEditxcoordinates.text().strip()
        y_text = self.dialog.lineEditycoordinate.text().strip()

        try:
            x = float(x_text)
            y = float(y_text)
        except ValueError:
            QMessageBox.warning(None, "Invalid Input", "Please enter valid numeric coordinates.")
            return

        coord_number = len(self.coordinates) + 1
        coord_text = f"{coord_number}) {x}, {y}"
        self.dialog.listWidgetlistofcoordinates.addItem(coord_text)
        self.coordinates.append(QgsPointXY(x, y))
        self.update_temp_coordinates_layer()
        self.update_lines()
        self.dialog.lineEditxcoordinates.clear()
        self.dialog.lineEditycoordinate.clear()

    def update_temp_coordinates_layer(self):
        """
        Updates the temporary point layer with all currently stored coordinates.
        """
        if not self.temp_coordinates_layer:
            self.create_temp_coordinates_layer()

        self.temp_coordinates_layer.startEditing()
        self.temp_coordinates_layer.dataProvider().truncate()
        self.temp_coordinates_layer.commitChanges()
        self.temp_coordinates_layer.startEditing()
        for idx, point in enumerate(self.coordinates, start=1):
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            feature.setAttributes([str(idx)])
            self.temp_coordinates_layer.addFeature(feature)
        self.temp_coordinates_layer.commitChanges()
        self.temp_coordinates_layer.updateExtents()
        self.temp_coordinates_layer.triggerRepaint()
        self.canvas.refresh()

    def update_lines(self):
        """
        Updates the rubber band to draw lines between consecutive points.
        """
        if not self.temp_lines_rubber_band:
            self.create_temp_coordinates_layer()

        self.temp_lines_rubber_band.reset(QgsWkbTypes.LineGeometry)
        for i in range(1, len(self.coordinates)):
            start_point = self.coordinates[i - 1]
            end_point = self.coordinates[i]
            self.temp_lines_rubber_band.addPoint(start_point)
            self.temp_lines_rubber_band.addPoint(end_point)

    def finish_coordinates_digitizing(self):
        """
        Finalizes the creation of a polygon from the list of coordinates and saves it as a shapefile.
        """
        if len(self.coordinates) < 3:
            QMessageBox.warning(None, "Error", "At least 3 coordinates are required to form a polygon.")
            return

        # Close the polygon if not already closed
        if self.coordinates[0] != self.coordinates[-1]:
            self.coordinates.append(self.coordinates[0])
            self.update_lines()

        epsg_code = self.dialog.lineEditEPSGcode.text().strip()
        if not epsg_code:
            QMessageBox.warning(None, "Error", "Please enter an EPSG code.")
            return

        try:
            crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg_code}")
            if not crs.isValid():
                QMessageBox.warning(None, "Error", "Invalid EPSG code.")
                return
        except:
            QMessageBox.warning(None, "Error", "Invalid EPSG code format.")
            return

        output_dir = QFileDialog.getExistingDirectory(None, "Select Output Directory")
        if not output_dir:
            return

        filename, ok = QInputDialog.getText(
            None,
            "Save Shapefile",
            "Enter filename (without extension):",
            text="area_by_coordinates",
        )
        if not ok or not filename:
            return

        # Create polygon from the coordinate list
        polygon = QgsGeometry.fromPolygonXY([self.coordinates.copy()])

        if not polygon.isGeosValid():
            QMessageBox.warning(None, "Error", "The created polygon is not valid. Please check your coordinates.")
            return

        # Create the final layer in memory
        final_layer = QgsVectorLayer(f"Polygon?crs=EPSG:{epsg_code}", filename, "memory")
        if not final_layer.isValid():
            QMessageBox.warning(None, "Error", "Failed to create the final layer.")
            return

        provider = final_layer.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.String)])
        final_layer.updateFields()

        # Add feature to the final layer
        feature = QgsFeature()
        feature.setGeometry(polygon)
        feature.setAttributes(["1"])
        provider.addFeature(feature)
        final_layer.commitChanges()

        output_path = os.path.join(output_dir, f"{filename}.shp")

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        options.layerName = filename

        # Transform geometry if needed
        if final_layer.crs() != crs:
            transform = QgsCoordinateTransform(final_layer.crs(), crs, QgsProject.instance())
            polygon.transform(transform)

        # Write the final shapefile
        write_result, error_message = QgsVectorFileWriter.writeAsVectorFormatV2(
            final_layer,
            output_path,
            QgsProject.instance().transformContext(),
            options,
        )

        if write_result == QgsVectorFileWriter.NoError:
            # Cleanup temporary layers and rubber bands
            if self.temp_coordinates_layer:
                QgsProject.instance().removeMapLayer(self.temp_coordinates_layer.id())
                self.temp_coordinates_layer = None
            if self.temp_lines_rubber_band:
                self.temp_lines_rubber_band.reset(QgsWkbTypes.LineGeometry)
                self.temp_lines_rubber_band = None

            self.coordinates = []

            new_layer = QgsVectorLayer(output_path, filename, "ogr")
            if new_layer.isValid():
                new_layer.setCrs(crs)
                QgsProject.instance().addMapLayer(new_layer)
                QMessageBox.information(
                    None,
                    "Success",
                    f"Shapefile saved successfully:\n{output_path}",
                )
            else:
                QMessageBox.warning(None, "Error", "Failed to load the saved shapefile.")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save shapefile: {error_message}")

    def remove_last_coordinate(self, item):
        """
        Removes the last coordinate from the list when double-clicking an item in the list widget.
        """
        if self.coordinates:
            self.coordinates.pop()
            self.dialog.listWidgetlistofcoordinates.takeItem(self.dialog.listWidgetlistofcoordinates.count() - 1)
            self.update_temp_coordinates_layer()
            self.update_lines()

    def add_feature(self, geometry, feature_type, map_tool):
        """
        Adds a new feature (polygon or circle) to the temporary sampling layer after user input for an ID.
        Validates geometry to avoid invalid or infinite coordinate issues.
        """
        if not geometry.isGeosValid():
            QMessageBox.warning(None, "Error", "Invalid geometry. Please try again.")
            map_tool.reset()
            return False

        id_value, ok = QInputDialog.getText(None, "Enter ID", "Enter ID for the feature:")
        if ok and id_value:
            feature = QgsFeature()
            feature.setGeometry(geometry)
            feature.setAttributes([id_value, feature_type])

            # Validate each coordinate to avoid infinite or NaN values
            for point in geometry.vertices():
                if not (isinstance(point.x(), (int, float)) and isinstance(point.y(), (int, float))):
                    QMessageBox.warning(None, "Error", "Invalid coordinates detected. Please try again.")
                    map_tool.reset()
                    return False
                if (math.isinf(point.x()) or math.isinf(point.y()) or math.isnan(point.x()) or math.isnan(point.y())):
                    QMessageBox.warning(None, "Error", "Invalid coordinates detected. Please try again.")
                    map_tool.reset()
                    return False

            if feature_type in ["area", "circle"]:
                self.temp_sampling_layer.startEditing()
                if self.temp_sampling_layer.addFeature(feature):
                    if self.temp_sampling_layer.commitChanges():
                        self.temp_sampling_layer.updateExtents()
                        self.temp_sampling_layer.triggerRepaint()
                        self.canvas.refresh()
                        self.feature_id += 1
                        return True
                    else:
                        self.temp_sampling_layer.rollBack()
                        QMessageBox.warning(
                            None,
                            "Error",
                            f"Failed to save feature: {self.temp_sampling_layer.commitErrors()}",
                        )
                else:
                    self.temp_sampling_layer.rollBack()
                    QMessageBox.warning(None, "Error", "Failed to add feature to layer.")
            else:
                QMessageBox.warning(None, "Error", "Unknown feature type.")
        else:
            map_tool.reset()

        return False

    def save_final_shapefile(self):
        """
        Saves the digitized features from the temporary sampling layer to an ESRI Shapefile.
        """
        if not self.temp_sampling_layer or self.temp_sampling_layer.featureCount() == 0:
            QMessageBox.warning(None, "Error", "No features to save. Please digitize areas first.")
            return

        epsg_code = self.dialog.lineEditEPSGcode.text().strip()
        if not epsg_code:
            QMessageBox.warning(None, "Error", "Please enter an EPSG code.")
            return

        try:
            crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg_code}")
            if not crs.isValid():
                QMessageBox.warning(None, "Error", "Invalid EPSG code.")
                return
        except:
            QMessageBox.warning(None, "Error", "Invalid EPSG code format.")
            return

        output_dir = QFileDialog.getExistingDirectory(None, "Select Output Directory")
        if not output_dir:
            return

        filename, ok = QInputDialog.getText(
            None,
            "Save Shapefile",
            "Enter filename (without extension):",
            text="sample_areas",
        )
        if not ok or not filename:
            return

        output_path = os.path.join(output_dir, f"{filename}.shp")

        # Collect valid features to avoid saving invalid geometries
        valid_features = []
        for feature in self.temp_sampling_layer.getFeatures():
            if feature.hasGeometry() and feature.geometry().isGeosValid():
                valid_features.append(feature)

        if not valid_features:
            QMessageBox.warning(None, "Error", "No valid features to save.")
            return

        # If CRS differs, create a transform
        if self.temp_sampling_layer.crs() != crs:
            transform = QgsCoordinateTransform(
                self.temp_sampling_layer.crs(), crs, QgsProject.instance()
            )
        else:
            transform = None

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        options.layerName = filename

        if transform:
            options.ct = transform

        # Write to shapefile
        write_result, error_message = QgsVectorFileWriter.writeAsVectorFormatV2(
            self.temp_sampling_layer,
            output_path,
            QgsProject.instance().transformContext(),
            options,
        )

        if write_result == QgsVectorFileWriter.NoError:
            # Remove temporary layer
            QgsProject.instance().removeMapLayer(self.temp_sampling_layer.id())
            self.temp_sampling_layer = None

            # Add final layer to project
            new_layer = QgsVectorLayer(output_path, filename, "ogr")
            if new_layer.isValid():
                new_layer.setCrs(crs)
                QgsProject.instance().addMapLayer(new_layer)
                QMessageBox.information(
                    None,
                    "Success",
                    f"Shapefile saved successfully:\n{output_path}",
                )
            else:
                QMessageBox.warning(None, "Error", "Failed to load the saved shapefile.")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save shapefile: {error_message}")


class AreaDigitizingTool(QgsMapToolEmitPoint):
    """
    This tool allows drawing polygons on the map canvas by left-clicking to add points
    and right-clicking to finalize the geometry.
    """
    def __init__(self, iface, area_exclusion):
        super().__init__(iface.mapCanvas())
        self.iface = iface  # Reference to QGIS interface
        self.canvas = iface.mapCanvas()  # Map canvas
        self.area_exclusion = area_exclusion  # Access to the parent module
        self.points = []  # Stores clicked points
        self.rubber_band = None  # For displaying the polygon
        self.temp_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.temp_rubber_band.setColor(QColor(255, 0, 0))
        self.temp_rubber_band.setWidth(2)

    def canvasPressEvent(self, event):
        """
        Captures mouse clicks. Left-click to add a new point, right-click to finish the polygon.
        """
        if event.button() == Qt.LeftButton:
            point = self.toMapCoordinates(event.pos())
            self.add_point(point)
        elif event.button() == Qt.RightButton:
            self.finish_polygon()

    def canvasMoveEvent(self, event):
        """
        Updates the temporary line to show the segment from the last added point to the current mouse position.
        """
        if not self.rubber_band:
            self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rubber_band.setColor(QColor(255, 0, 0, 100))
            self.rubber_band.setWidth(2)

        current_point = self.toMapCoordinates(event.pos())

        if self.points:
            self.temp_rubber_band.reset(QgsWkbTypes.LineGeometry)
            self.temp_rubber_band.addPoint(self.points[-1])
            self.temp_rubber_band.addPoint(current_point)

        if len(self.points) > 0:
            points_to_draw = self.points + [current_point]
            if len(points_to_draw) > 2:
                self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
                for pt in points_to_draw:
                    self.rubber_band.addPoint(pt)

    def add_point(self, point):
        """
        Adds a point to the list and updates the polygon rubber band.
        """
        self.points.append(point)
        if not self.rubber_band:
            self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rubber_band.setColor(QColor(255, 0, 0, 100))
            self.rubber_band.setWidth(2)

        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        for pt in self.points:
            self.rubber_band.addPoint(pt)

    def finish_polygon(self):
        """
        Finalizes the polygon if there are enough points, then sends it to be saved.
        """
        if len(self.points) < 3:
            QMessageBox.warning(None, "Error", "A polygon must have at least 3 points.")
            return

        # Close polygon if not closed
        if self.points[0] != self.points[-1]:
            self.points.append(self.points[0])

        geometry = QgsGeometry.fromPolygonXY([self.points])
        if self.area_exclusion.add_feature(geometry, "area", self):
            self.reset()

    def reset(self):
        """
        Clears the rubber bands and points after finishing or canceling the feature.
        """
        self.points = []
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.temp_rubber_band.reset(QgsWkbTypes.LineGeometry)


class CircleDigitizingTool(QgsMapToolEmitPoint):
    """
    This tool allows drawing circles on the map canvas.
    Left-click to set the circle center, right-click to finalize by setting the radius.
    """
    def __init__(self, iface, area_exclusion):
        super().__init__(iface.mapCanvas())
        self.iface = iface  # Reference to QGIS interface
        self.canvas = iface.mapCanvas()  # Map canvas
        self.area_exclusion = area_exclusion  # Access to the parent module
        self.center = None  # Stores the center of the circle
        self.rubber_band = None  # Displays the circle
        self.temp_rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.temp_rubber_band.setColor(QColor(0, 0, 255))
        self.temp_rubber_band.setWidth(2)

    def canvasPressEvent(self, event):
        """
        Left-click sets the center, right-click completes the circle with the distance as the radius.
        """
        if event.button() == Qt.LeftButton:
            self.set_center(self.toMapCoordinates(event.pos()))
        elif event.button() == Qt.RightButton and self.center:
            point = self.toMapCoordinates(event.pos())
            self.finish_circle(point)

    def canvasMoveEvent(self, event):
        """
        Draws a temporary line to indicate the radius of the circle while moving the mouse.
        """
        if self.center:
            point = self.toMapCoordinates(event.pos())

            if not self.rubber_band:
                self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
                self.rubber_band.setColor(QColor(0, 0, 255, 100))
                self.rubber_band.setWidth(2)

            self.temp_rubber_band.reset(QgsWkbTypes.LineGeometry)
            self.temp_rubber_band.addPoint(self.center)
            self.temp_rubber_band.addPoint(point)

            radius = self.center.distance(point)
            self.draw_circle(radius)

    def set_center(self, point):
        """
        Sets the circle's center point.
        """
        self.center = point
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def draw_circle(self, radius):
        """
        Re-draws the circle rubber band with a given radius around the stored center.
        """
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

            points = []
            segments = 72  # Defines how smooth the circle is
            for i in range(segments + 1):
                theta = i * (2 * math.pi / segments)
                x = self.center.x() + radius * math.cos(theta)
                y = self.center.y() + radius * math.sin(theta)
                points.append(QgsPointXY(x, y))

            self.rubber_band.setToGeometry(QgsGeometry.fromPolygonXY([points]), None)

    def finish_circle(self, point):
        """
        Creates the final circle geometry and sends it to be saved in the temporary sampling layer.
        """
        if self.center:
            radius = self.center.distance(point)
            points = []
            segments = 72
            for i in range(segments + 1):
                theta = i * (2 * math.pi / segments)
                x = self.center.x() + radius * math.cos(theta)
                y = self.center.y() + radius * math.sin(theta)
                points.append(QgsPointXY(x, y))

            geometry = QgsGeometry.fromPolygonXY([points])
            if self.area_exclusion.add_feature(geometry, "circle", self):
                self.reset()

    def reset(self):
        """
        Clears the circle after finishing or canceling.
        """
        self.center = None
        if self.rubber_band:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.temp_rubber_band.reset(QgsWkbTypes.LineGeometry)
