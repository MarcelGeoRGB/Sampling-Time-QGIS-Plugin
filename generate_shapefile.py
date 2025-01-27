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
 *   along with Sampling Time Plugin. If not, see                          *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/
"""
# This script provides functionality for stratified shapefile creation in QGIS.

import os  # Provides a portable way of using operating system dependent functionality
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QLineEdit
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsPointXY, QgsField, QgsSymbol, QgsSingleSymbolRenderer,
                       QgsVectorFileWriter, QgsSvgMarkerSymbolLayer, QgsWkbTypes,
                       QgsFeatureRequest, QgsSpatialIndex, QgsRectangle, QgsDistanceArea,
                       QgsPoint, QgsPolygon, QgsCoordinateReferenceSystem, QgsFields)
from qgis.PyQt.QtCore import Qt, QVariant, QObject
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker, QgsMapToolEmitPoint, QgsMapToolEdit
from qgis.PyQt.QtGui import QColor
from qgis import processing


class Stratifiedshapefile(QObject):
    # This class manages the creation of stratified shapefiles (via lines, polylines, or Voronoi).
    def __init__(self, iface, dialog):
        # Constructor initializes references, variables, and connects UI elements.
        super().__init__()
        self.iface = iface  # Reference to QGIS interface
        self.dialog = dialog  # Reference to the plugin's dialog
        self.canvas = iface.mapCanvas() if iface else None  # Map canvas reference
        self.sampling_area = None  # Stores the selected sampling area layer
        self.strata_layer = None  # Will store resulting strata polygons
        self.temp_layer = None  # Temporary layer placeholder
        self.line_tool = None  # Tool for freehand line drawing
        self.polyline_tool = None  # Tool for polyline drawing
        self.point_tool = None  # Tool for point addition
        self.rubber_band = None  # Rubber band for visual feedback
        self.points = []  # List of points for Voronoi
        self.lines = []  # List of lines for strata creation
        self.polylines = []  # List of polylines for strata creation
        self.voronoi_layer = None  # Layer for Voronoi polygons
        self.drawing = False  # Flag to indicate if drawing is active
        self.edit_tool = None  # Tool for editing, not used in this snippet

        self.setup_ui_connections()  # Calls function to set up UI connections

    def setup_ui_connections(self):
        # This method configures signals and slots for UI widgets (buttons, checkboxes).
        self.dialog.pushButtonstratastart_lines.setEnabled(False)
        self.dialog.pushButtonstratafinish_lines.setEnabled(False)
        self.dialog.pushButtonstratastart_voronoi.setEnabled(False)
        self.dialog.pushButtonstratafinish_voronoi.setEnabled(False)
        self.dialog.pushButtonstratastart_polyline.setEnabled(False)
        self.dialog.pushButtonstratafinish_polyline.setEnabled(False)

        # Connect Function 1 (lines) checkboxes and buttons
        self.dialog.checkBoxstratalines.stateChanged.connect(self.toggle_stratalines)
        self.dialog.pushButtonstratastart_lines.clicked.connect(self.start_drawing_lines)
        self.dialog.pushButtonstratafinish_lines.clicked.connect(self.finish_drawing_lines)

        # Connect Function 2 (Voronoi) checkboxes and buttons
        self.dialog.checkBoxstratavoronoi.stateChanged.connect(self.toggle_stratavoronoi)
        self.dialog.pushButtonstratastart_voronoi.clicked.connect(self.start_adding_points)
        self.dialog.pushButtonstratafinish_voronoi.clicked.connect(self.finish_adding_points)

        # Connect Function 3 (polylines) checkboxes and buttons
        self.dialog.checkBoxstratapolyline.stateChanged.connect(self.toggle_stratapolyline)
        self.dialog.pushButtonstratastart_polyline.clicked.connect(self.start_drawing_polylines)
        self.dialog.pushButtonstratafinish_polyline.clicked.connect(self.finish_drawing_polylines)

        # Ensure that only one checkbox can be active at once
        self.dialog.checkBoxstratalines.toggled.connect(self.ensure_single_selection)
        self.dialog.checkBoxstratavoronoi.toggled.connect(self.ensure_single_selection)
        self.dialog.checkBoxstratapolyline.toggled.connect(self.ensure_single_selection)

    def ensure_single_selection(self, checked):
        # This method makes sure no more than one checkbox is selected at the same time.
        sender = self.dialog.sender()
        if checked:
            if sender != self.dialog.checkBoxstratalines:
                self.dialog.checkBoxstratalines.setChecked(False)
            if sender != self.dialog.checkBoxstratavoronoi:
                self.dialog.checkBoxstratavoronoi.setChecked(False)
            if sender != self.dialog.checkBoxstratapolyline:
                self.dialog.checkBoxstratapolyline.setChecked(False)

    ######################
    # Function 1 Methods #
    ######################

    def toggle_stratalines(self, state):
        # Enables/disables relevant buttons for drawing strata lines.
        self.dialog.pushButtonstratastart_lines.setEnabled(state == Qt.Checked)
        self.dialog.pushButtonstratafinish_lines.setEnabled(state == Qt.Checked)
        if state == Qt.Checked:
            msg = (
                "Tool Usage Instructions:\n\n"
                "- Press the start button to initiate the process.\n"
                "Draw Lines for Strata:\n"
                "- Left-click to start drawing a line.\n"
                "- Move the mouse to draw freely.\n"
                "- Right-click to delete the last line.\n"
                "- Repeat as necessary.\n"
                "- Click 'Finish' to generate strata polygons."
            )
            QMessageBox.information(None, "Instructions", msg)

    def start_drawing_lines(self):
        # Begins the freehand line drawing process.
        if not self.sampling_area:
            self.load_sampling_area()
        if not self.sampling_area:
            QMessageBox.warning(None, "Error", "Sampling area not loaded.")
            return

        self.drawing = True
        self.line_tool = FreehandLineDrawingTool(self.iface, self)
        self.canvas.setMapTool(self.line_tool)
        print("Starting to draw lines for strata.")

        self.dialog.showMinimized()  # Minimizes the plugin window to see the map

    def finish_drawing_lines(self):
        # Completes the line drawing and triggers strata polygon generation.
        if not self.lines:
            QMessageBox.warning(None, "No Lines Drawn", "No lines were drawn.")
            return

        print("Converting lines to strata polygons.")
        self.generate_strata_from_lines(self.lines, "strata_lines")

        self.lines = []  # Clears stored lines
        if self.rubber_band:
            self.rubber_band.reset(True)
        self.drawing = False
        self.canvas.unsetMapTool(self.line_tool)
        self.line_tool = None

    ######################
    # Function 2 Methods #
    ######################

    def toggle_stratavoronoi(self, state):
        # Enables/disables relevant buttons for generating Voronoi polygons.
        self.dialog.pushButtonstratastart_voronoi.setEnabled(state == Qt.Checked)
        self.dialog.pushButtonstratafinish_voronoi.setEnabled(state == Qt.Checked)
        if state == Qt.Checked:
            msg = (
                "Tool Usage Instructions:\n\n"
                "- Press the start button to initiate the process.\n"
                "Add Points for Voronoi Strata:\n"
                "- Click on the map to add a point.\n"
                "- Repeat to add multiple points.\n"
                "- Click 'Finish' to generate Voronoi polygons."
            )
            QMessageBox.information(None, "Instructions", msg)

    def start_adding_points(self):
        # Begins the process of adding points for Voronoi generation.
        if not self.sampling_area:
            self.load_sampling_area()
        if not self.sampling_area:
            QMessageBox.warning(None, "Error", "Sampling area not loaded.")
            return

        self.drawing = True
        self.point_tool = PointAddingTool(self.iface, self)
        self.canvas.setMapTool(self.point_tool)
        print("Starting to add points for Voronoi strata.")

        self.dialog.showMinimized()

    def finish_adding_points(self):
        # Completes point addition and triggers Voronoi polygon generation.
        if not self.points:
            QMessageBox.warning(None, "No Points Added", "No points were added.")
            return

        print("Generating Voronoi polygons from points.")
        self.generate_voronoi_polygons()

        self.points = []  # Clears stored points
        if self.rubber_band:
            self.rubber_band.reset(True)
        self.drawing = False
        self.canvas.unsetMapTool(self.point_tool)
        self.point_tool = None

    ######################
    # Function 3 Methods #
    ######################

    def toggle_stratapolyline(self, state):
        # Enables/disables relevant buttons for drawing polylines.
        self.dialog.pushButtonstratastart_polyline.setEnabled(state == Qt.Checked)
        self.dialog.pushButtonstratafinish_polyline.setEnabled(state == Qt.Checked)
        if state == Qt.Checked:
            msg = (
                "Tool Usage Instructions:\n\n"
                "- Press the start button to initiate the process.\n"
                "Draw Polylines for Strata:\n"
                "- Left-click to add vertices.\n"
                "- Double left-click to finish a polyline.\n"
                "- Right-click to delete the last polyline.\n"
                "- Press Ctrl to constrain lines to horizontal or vertical.\n"
                "- Click 'Finish' to generate strata polygons."
            )
            QMessageBox.information(None, "Instructions", msg)

    def start_drawing_polylines(self):
        # Begins the process of drawing polylines.
        if not self.sampling_area:
            self.load_sampling_area()
        if not self.sampling_area:
            QMessageBox.warning(None, "Error", "Sampling area not loaded.")
            return

        self.drawing = True
        self.polyline_tool = PolylineDrawingTool(self.iface, self)
        self.canvas.setMapTool(self.polyline_tool)
        print("Starting to draw polylines for strata.")

        self.dialog.showMinimized()

    def finish_drawing_polylines(self):
        # Completes polyline drawing and triggers strata generation.
        if not self.polylines:
            QMessageBox.warning(None, "No Polylines Drawn", "No polylines were drawn.")
            return

        print("Converting polylines to strata polygons.")
        self.generate_strata_from_lines(self.polylines, "strata_polyline")

        self.polylines = []  # Clears stored polylines
        if self.rubber_band:
            self.rubber_band.reset(True)
        self.drawing = False
        self.canvas.unsetMapTool(self.polyline_tool)
        self.polyline_tool = None

    ############################
    # Shared Helper Methods    #
    ############################

    def generate_strata_from_lines(self, lines_list, default_filename):
        # This method takes lists of line geometries and polygonizes them for stratification.
        line_layer = QgsVectorLayer("LineString?crs=" + self.sampling_area.crs().authid(), "Strata Lines", "memory")
        prov = line_layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("ID", QVariant.Int))
        prov.addAttributes(fields)
        line_layer.updateFields()

        feats = []
        for i, line in enumerate(lines_list):
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(line))
            feat.setAttributes([i])
            feats.append(feat)
        prov.addFeatures(feats)

        params_boundary = {
            'INPUT': self.sampling_area,
            'OUTPUT': 'memory:Boundary Lines'
        }
        boundary_result = processing.run('native:boundary', params_boundary)
        boundary_layer = boundary_result['OUTPUT']

        # Merges user-drawn lines with the boundary lines of the sampling area.
        line_layers = [line_layer, boundary_layer]
        params_merge = {
            'LAYERS': line_layers,
            'CRS': self.sampling_area.crs(),
            'OUTPUT': 'memory:Combined Lines'
        }
        merged_lines_result = processing.run('native:mergevectorlayers', params_merge)
        merged_lines_layer = merged_lines_result['OUTPUT']

        # Polygonizes merged lines to create strata polygons.
        params_polygonize = {
            'INPUT': merged_lines_layer,
            'KEEP_FIELDS': False,
            'OUTPUT': 'memory:Strata Polygons'
        }
        result_polygonize = processing.run("native:polygonize", params_polygonize)
        if result_polygonize['OUTPUT']:
            params_clip = {
                'INPUT': result_polygonize['OUTPUT'],
                'OVERLAY': self.sampling_area,
                'OUTPUT': 'memory:Clipped Strata Polygons'
            }
            clip_result = processing.run("native:intersection", params_clip)
            if clip_result['OUTPUT']:
                self.strata_layer = clip_result['OUTPUT']
                self.strata_layer.setName("Strata Polygons")

                self.remove_unnecessary_fields(self.strata_layer)  # Removes redundant fields
                self.add_strata_fields(self.strata_layer)  # Adds ID, Strata, and area fields

                # Prompts user to choose an output directory and file name.
                output_dir = QFileDialog.getExistingDirectory(self.dialog, "Select Output Directory", QgsProject.instance().homePath())
                if not output_dir:
                    QMessageBox.warning(None, "Cancelled", "Operation cancelled by the user.")
                    return

                filename, ok = QInputDialog.getText(self.dialog, "Save Shapefile", "Enter the file name (without extension):", QLineEdit.Normal, default_filename)
                if not ok or not filename:
                    QMessageBox.warning(None, "Cancelled", "Operation cancelled by the user.")
                    return

                output_path = os.path.join(output_dir, f"{filename}.shp")
                QgsVectorFileWriter.writeAsVectorFormat(self.strata_layer, output_path, "utf-8", self.strata_layer.crs(), "ESRI Shapefile")

                # Loads and adds the newly created shapefile to the QGIS project.
                saved_layer = QgsVectorLayer(output_path, filename, "ogr")
                if saved_layer.isValid():
                    QgsProject.instance().addMapLayer(saved_layer)
                    print(f"Strata polygons generated and saved at: {output_path}")
                    QMessageBox.information(None, "Success", f"Strata polygons generated and saved at:\n{output_path}")
                else:
                    QMessageBox.warning(None, "Error", "Failed to load the saved layer.")
            else:
                QMessageBox.warning(None, "Error", "Failed to clip the strata polygons with the sampling area.")
        else:
            QMessageBox.warning(None, "Error", "Failed to polygonize lines into strata polygons.")

    def add_strata_fields(self, layer):
        # Adds or ensures Strata, Area, and ID fields exist in the given layer.
        layer.startEditing()
        if layer.fields().indexFromName('Strata') == -1:
            layer.dataProvider().addAttributes([
                QgsField('Strata', QVariant.String)
            ])
            layer.updateFields()
        if layer.fields().indexFromName('Area_square_meters') == -1:
            layer.dataProvider().addAttributes([
                QgsField('Area_square_meters', QVariant.Double)
            ])
            layer.updateFields()
        if layer.fields().indexFromName('ID') == -1:
            layer.dataProvider().addAttributes([
                QgsField('ID', QVariant.Int)
            ])
            layer.updateFields()

        features = layer.getFeatures()
        area_calculator = QgsDistanceArea()
        area_calculator.setEllipsoid('WGS84')  # Adjust ellipsoid if needed
        area_calculator.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())

        # Assigns incremental ID, strata name, and calculates area for each feature.
        for idx, feature in enumerate(features, start=1):
            geom = feature.geometry()
            area = area_calculator.measureArea(geom)
            layer.changeAttributeValue(feature.id(), layer.fields().indexFromName('ID'), idx)
            layer.changeAttributeValue(feature.id(), layer.fields().indexFromName('Strata'), f"Strata {idx}")
            layer.changeAttributeValue(feature.id(), layer.fields().indexFromName('Area_square_meters'), area)

        layer.commitChanges()

    def remove_unnecessary_fields(self, layer):
        # Removes or renames unnecessary fields in the given layer.
        layer.startEditing()
        fields = layer.fields()
        field_names = [field.name() for field in fields]
        if 'id_2' in field_names:
            idx = layer.fields().indexFromName('id_2')
            layer.dataProvider().deleteAttributes([idx])
            layer.updateFields()
        if 'id' in field_names:
            idx = layer.fields().indexFromName('id')
            layer.renameAttribute(idx, 'ID')
            layer.updateFields()
        if 'strata' in field_names:
            idx = layer.fields().indexFromName('strata')
            layer.renameAttribute(idx, 'Strata')
            layer.updateFields()
        layer.commitChanges()

    def generate_voronoi_polygons(self):
        # This method builds Voronoi polygons from user-added points.
        point_layer = QgsVectorLayer("Point?crs=" + self.sampling_area.crs().authid(), "Voronoi Points", "memory")
        prov = point_layer.dataProvider()
        fields = QgsFields()
        fields.append(QgsField("ID", QVariant.Int))
        prov.addAttributes(fields)
        point_layer.updateFields()

        feats = []
        for i, point in enumerate(self.points):
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPointXY(point))
            feat.setAttributes([i])
            feats.append(feat)
        prov.addFeatures(feats)

        extent = point_layer.extent()
        width = extent.width()
        height = extent.height()
        buffer_distance = max(width, height) / 2  # Defines a buffer around the points

        params_voronoi = {
            'INPUT': point_layer,
            'BUFFER': buffer_distance,
            'OUTPUT': 'memory:Voronoi Polygons'
        }
        voronoi_result = processing.run("qgis:voronoipolygons", params_voronoi)

        if voronoi_result['OUTPUT']:
            params_clip = {
                'INPUT': voronoi_result['OUTPUT'],
                'OVERLAY': self.sampling_area,
                'OUTPUT': 'memory:Clipped Voronoi Polygons'
            }
            clip_result = processing.run("native:intersection", params_clip)
            if clip_result['OUTPUT']:
                self.strata_layer = clip_result['OUTPUT']
                self.strata_layer.setName("Voronoi Strata Polygons")

                self.remove_unnecessary_fields(self.strata_layer)
                self.add_strata_fields(self.strata_layer)

                output_dir = QFileDialog.getExistingDirectory(self.dialog, "Select Output Directory", QgsProject.instance().homePath())
                if not output_dir:
                    QMessageBox.warning(None, "Cancelled", "Operation cancelled by the user.")
                    return

                filename, ok = QInputDialog.getText(self.dialog, "Save Shapefile", "Enter the file name (without extension):", QLineEdit.Normal, "voronoi_strata")
                if not ok or not filename:
                    QMessageBox.warning(None, "Cancelled", "Operation cancelled by the user.")
                    return

                output_path = os.path.join(output_dir, f"{filename}.shp")
                QgsVectorFileWriter.writeAsVectorFormat(self.strata_layer, output_path, "utf-8", self.strata_layer.crs(), "ESRI Shapefile")

                saved_layer = QgsVectorLayer(output_path, filename, "ogr")
                if saved_layer.isValid():
                    QgsProject.instance().addMapLayer(saved_layer)
                    print(f"Voronoi strata polygons generated and saved at: {output_path}")
                    QMessageBox.information(None, "Success", f"Voronoi strata polygons generated and saved at:\n{output_path}")
                else:
                    QMessageBox.warning(None, "Error", "Failed to load the saved layer.")
            else:
                QMessageBox.warning(None, "Error", "Failed to clip the Voronoi polygons with the sampling area.")
        else:
            QMessageBox.warning(None, "Error", "Failed to generate Voronoi polygons.")

    ############################
    # Helper and Utility Methods #
    ############################

    def load_sampling_area(self):
        # Loads the sampling area selected in comboBoxshpsampling.
        layer_name = self.dialog.comboBoxshpsampling.currentText().split(" [")[0]
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if layers:
            self.sampling_area = layers[0]
            print(f"Sampling area loaded: {self.sampling_area.name()}")
        else:
            QMessageBox.warning(None, "Error", "Sampling area not found.")
            print("Sampling area not found.")

    def deactivate_current_tool(self):
        # Deactivates the current map tool if any is set.
        self.canvas.unsetMapTool(self.canvas.mapTool())


class FreehandLineDrawingTool(QgsMapTool):
    # This map tool allows freehand line drawing on the QGIS canvas.
    def __init__(self, iface, stratified_sampling):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.stratified_sampling = stratified_sampling
        self.points = []
        self.is_drawing = False
        self.rubber_band = None
        self.rubber_bands = []

    def canvasPressEvent(self, event):
        # Starts drawing a line if the left mouse button is pressed.
        if event.button() == Qt.LeftButton:
            self.is_drawing = True
            self.points = []
            point = self.toMapCoordinates(event.pos())
            self.points.append(point)
            self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.rubber_band.setColor(QColor(255, 0, 0))
            self.rubber_band.setWidth(2)
            self.rubber_band.addPoint(point)
            self.rubber_bands.append(self.rubber_band)
        elif event.button() == Qt.RightButton:
            # Deletes the last drawn line if the right mouse button is pressed.
            if self.rubber_bands:
                last_rubber_band = self.rubber_bands.pop()
                self.canvas.scene().removeItem(last_rubber_band)
                if self.stratified_sampling.lines:
                    self.stratified_sampling.lines.pop()

    def canvasMoveEvent(self, event):
        # Continues adding points to the current line as the mouse moves.
        if self.is_drawing:
            point = self.toMapCoordinates(event.pos())
            self.points.append(point)
            self.rubber_band.addPoint(point)

    def canvasReleaseEvent(self, event):
        # Ends the line creation on left button release.
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            if len(self.points) > 1:
                self.stratified_sampling.lines.append(self.points.copy())
            else:
                QMessageBox.warning(None, "Invalid Line", "A line must have at least two points.")
                self.canvas.scene().removeItem(self.rubber_band)
                self.rubber_bands.remove(self.rubber_band)
            self.points = []
            self.rubber_band = None

    def deactivate(self):
        # Removes remaining rubber bands when the tool is deactivated.
        super().deactivate()
        for rb in self.rubber_bands:
            self.canvas.scene().removeItem(rb)
        self.rubber_bands = []
        self.rubber_band = None

    def activate(self):
        # Sets the cursor to cross when the tool is activated.
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)


class PolylineDrawingTool(QgsMapTool):
    # This map tool allows controlled polyline drawing (with optional constraints).
    def __init__(self, iface, stratified_sampling):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.stratified_sampling = stratified_sampling
        self.points = []
        self.is_drawing = False
        self.rubber_band = None
        self.rubber_bands = []
        self.last_constrained_point = None

    def canvasPressEvent(self, event):
        # Starts or continues the drawing of a polyline based on mouse button actions.
        if event.button() == Qt.LeftButton:
            if not self.is_drawing:
                point = self.toMapCoordinates(event.pos())
                self.is_drawing = True
                self.points = [point]
                self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
                self.rubber_band.setColor(QColor(0, 255, 0))
                self.rubber_band.setWidth(2)
                self.rubber_band.addPoint(point)
                self.rubber_bands.append(self.rubber_band)
                self.last_constrained_point = point
            else:
                self.points.append(self.last_constrained_point)
                self.rubber_band.addPoint(self.last_constrained_point)
        elif event.button() == Qt.RightButton:
            # Deletes the last polyline drawn if the right mouse button is pressed.
            if self.rubber_bands:
                last_rubber_band = self.rubber_bands.pop()
                self.canvas.scene().removeItem(last_rubber_band)
                if self.stratified_sampling.polylines:
                    self.stratified_sampling.polylines.pop()
            self.is_drawing = False
            self.points = []
            self.rubber_band = None
            self.last_constrained_point = None

    def canvasMoveEvent(self, event):
        # Handles the constraint logic (horizontal/vertical) when Ctrl is held.
        if self.is_drawing:
            point = self.toMapCoordinates(event.pos())
            if event.modifiers() & Qt.ControlModifier and len(self.points) > 0:
                last_point = self.points[-1]
                delta_x = point.x() - last_point.x()
                delta_y = point.y() - last_point.y()
                if abs(delta_x) > abs(delta_y):
                    constrained_point = QgsPointXY(point.x(), last_point.y())
                else:
                    constrained_point = QgsPointXY(last_point.x(), point.y())
                point_to_add = constrained_point
            else:
                point_to_add = point

            self.last_constrained_point = point_to_add

            if self.rubber_band.numberOfVertices() > len(self.points):
                self.rubber_band.removePoint(-1)
            self.rubber_band.addPoint(point_to_add)

            self.canvas.refresh()

    def canvasDoubleClickEvent(self, event):
        # Finishes the polyline on double left-click.
        if self.is_drawing and len(self.points) > 0:
            self.points.append(self.last_constrained_point)
            self.is_drawing = False
            if self.rubber_band.numberOfVertices() > len(self.points):
                self.rubber_band.removePoint(-1)
            self.stratified_sampling.polylines.append(self.points.copy())
            self.points = []
            self.rubber_band = None
            self.last_constrained_point = None
        else:
            QMessageBox.warning(None, "Invalid Polyline", "A polyline must have at least two points.")
            if self.rubber_band:
                self.canvas.scene().removeItem(self.rubber_band)
                self.rubber_bands.remove(self.rubber_band)
            self.is_drawing = False
            self.points = []
            self.rubber_band = None
            self.last_constrained_point = None

    def deactivate(self):
        # Cleans up any remaining rubber bands when the tool is deactivated.
        super().deactivate()
        for rb in self.rubber_bands:
            self.canvas.scene().removeItem(rb)
        self.rubber_bands = []
        self.rubber_band = None
        self.is_drawing = False
        self.points = []
        self.last_constrained_point = None

    def activate(self):
        # Sets the cursor to cross when the tool is activated.
        super().activate()
        self.canvas.setCursor(Qt.CrossCursor)


class PointAddingTool(QgsMapToolEmitPoint):
    # This tool allows the user to add points on the canvas (used for Voronoi).
    def __init__(self, iface, stratified_sampling):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.stratified_sampling = stratified_sampling
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
        self.rubber_band.setColor(QColor(0, 0, 255))
        self.rubber_band.setIconSize(5)
        self.rubber_band.setIcon(QgsRubberBand.ICON_CIRCLE)

    def canvasReleaseEvent(self, event):
        # Adds a point to the list and displays it with a rubber band circle.
        point = self.toMapCoordinates(event.pos())
        self.stratified_sampling.points.append(point)
        self.rubber_band.addPoint(point, True)

    def deactivate(self):
        # Removes the point rubber band when the tool is deactivated.
        super().deactivate()
        if self.rubber_band:
            self.canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None

    def activate(self):
        # Recreates the rubber band if the tool is reactivated.
        super().activate()
        if not self.rubber_band:
            self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PointGeometry)
            self.rubber_band.setColor(QColor(0, 0, 255))
            self.rubber_band.setIconSize(5)
            self.rubber_band.setIcon(QgsRubberBand.ICON_CIRCLE)
