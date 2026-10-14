import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import MeshDesk 1.0

Item {
    id: view; property var app
    property var activeLayers: ["nodes","waypoints"]
    property bool nodePopup: false
    property string hoverText: ""
    property real hoverX: 0
    property real hoverY: 0
    NodeFilters { id: filters; app: view.app }
    function toggleLayer(name,on) { if(on && (name==="heat" || name==="snr")){activeLayers=[name];return;} var next=activeLayers.slice();var i=next.indexOf(name);if(on && i<0)next.push(name);if(!on && i>=0)next.splice(i,1);activeLayers=next; }
    MeshMap {
        id: map; objectName: "meshMap"; anchors.fill: parent
        nodes: app ? app.s.filtered_nodes : []; myNode: app ? String(app.s.my_num) : "0"; waypoints: app ? app.s.waypoints || [] : []; layers: view.activeLayers
        online: app && app.s.online_maps; tileUrl: app ? app.s.tile_url : ""; attribution: app ? app.s.tile_attribution : ""
        onNodeClicked: function(num) {app.act("node",{num:num});view.nodePopup=true;}
        onWaypointClicked: function(waypointId) {app.act("waypoint_details",{id:waypointId});}
        onCoordinateClicked: function(lat,lon) {latitude.text=lat.toFixed(7);longitude.text=lon.toFixed(7);waypointDialog.open();}
        Component.onCompleted: fitTimer.start()
    }
    Connections {
        target: view.app
        function onSChanged() {if(app && app.s.notification.message === "Computer location")map.center(app.s.notification.latitude,app.s.notification.longitude);}
    }
    Timer { id: fitTimer; objectName: "mapInitialFit"; interval: 200; onTriggered: {
        var n=app ? app.s.selected_node : null;var p=n ? n.position : null;
        if(p && p.latitude !== undefined)map.center(p.latitude,p.longitude);
        else if(p && p.latitudeI !== undefined)map.center(p.latitudeI*1e-7,p.longitudeI*1e-7);
        else map.fit();
    } }
    PinchArea {
        anchors.fill: parent
        property real lastScale: 1
        onPinchStarted: lastScale=1
        onPinchUpdated: {if(pinch.scale/lastScale>1.4){map.changeZoom(1);lastScale=pinch.scale;}else if(pinch.scale/lastScale<0.7){map.changeZoom(-1);lastScale=pinch.scale;}}
        MouseArea {
            hoverEnabled: true
            anchors.fill: parent; property real previousX; property real previousY; property real startX; property real startY
            onPressed: {previousX=mouse.x;previousY=mouse.y;startX=mouse.x;startY=mouse.y;}
            onPositionChanged: {if(pressed){map.pan(mouse.x-previousX,mouse.y-previousY);previousX=mouse.x;previousY=mouse.y;view.hoverText="";}else{view.hoverX=mouse.x;view.hoverY=mouse.y;view.hoverText=map.infoAt(mouse.x,mouse.y);}}
            onExited: view.hoverText=""
            onReleased: if(Math.abs(mouse.x-startX)+Math.abs(mouse.y-startY)<8)map.click(mouse.x,mouse.y)
            onWheel: map.changeZoom(wheel.angleDelta.y>0 ? 1 : -1)
            onDoubleClicked: map.changeZoom(1)
        }
    }
    Rectangle {
        visible: view.hoverText.length>0; z: 4; color: app.panel; radius: 6
        x: Math.max(4,Math.min(view.width-width-4,view.hoverX+12)); y: Math.max(4,Math.min(view.height-height-30,view.hoverY+12))
        width: Math.min(300,hoverLabel.implicitWidth+20); height: hoverLabel.implicitHeight+16
        Label { textFormat: Text.PlainText; id: hoverLabel; anchors.centerIn: parent; text: view.hoverText; color: app.ink; font.pixelSize: 12 }
    }
    Rectangle {
        visible: view.nodePopup && app && !!app.s.selected_node.num
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 14; anchors.bottomMargin: 78
        width: Math.min(380,parent.width-28); height: nodeCard.implicitHeight+24; radius: 10; color: app.panel
        ColumnLayout {
            id: nodeCard; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
            RowLayout {
                Label { textFormat: Text.PlainText; text: app.s.selected_node.name || ""; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: true }
                MeshToolButton { text: "×"; onClicked: view.nodePopup=false }
            }
            Label { textFormat: Text.PlainText; text: app.s.selected_node.num ? "!"+Number(app.s.selected_node.num).toString(16) : ""; color: app.accent }
            Label { textFormat: Text.PlainText; text: "SNR: "+(app.s.selected_node.snr===undefined ? "—" : app.s.selected_node.snr)+" dB"; color: app.muted }
            Flow {
                Layout.fillWidth: true; spacing: 4
                MeshButton { text: app.tr("Message"); enabled: app.s.selected_node.num!==app.s.my_num; onClicked: {app.act("chat",{peer:app.s.selected_node.num});app.go("Chat");} }
                MeshButton { text: app.tr("Node information"); onClicked: app.go("Nodes") }
                MeshButton { text: app.s.selected_node.favorite ? "★" : "☆"; enabled: app.s.connected; onClicked: app.act("command",{name:app.s.selected_node.favorite ? "unfavorite" : "favorite",args:{value:app.s.selected_node.num}}) }
            }
        }
    }
    Flow {
        anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 15; spacing: 4
        MeshButton { text: app ? app.tr("Layers") : "Layers"; onClicked: layersMenu.open(); Menu {
            id: layersMenu; objectName: "mapLayersMenu"
            Repeater { model: [{key:"nodes",name:"Nodes"},{key:"waypoints",name:"Waypoints"},{key:"direct",name:"Direct neighbors"},{key:"remote",name:"Remote neighbors"},{key:"precision",name:"Position precision"},{key:"heat",name:"Node density"},{key:"snr",name:"Signal strength"}]
                delegate: MenuItem { text: app.tr(modelData.name); checkable: true; checked: view.activeLayers.indexOf(modelData.key)>=0; onToggled: view.toggleLayer(modelData.key,checked) }
            }
        } }
        MeshButton { text: app ? app.tr("Fit mesh") : "Fit mesh"; onClicked: map.fit() }
        MeshButton { text: app.tr("Filters"); onClicked: filters.open() }
        MeshButton { text: app.tr("Locate"); onClicked: locateMenu.open(); Menu {
            id: locateMenu; objectName: "mapLocateMenu"
            MenuItem { text: app.tr("My radio"); onTriggered: {for(var i=0;i<app.s.nodes.length;i++){var n=app.s.nodes[i];if(n.num===app.s.my_num && n.position){var p=n.position;map.center(p.latitude!==undefined ? p.latitude : p.latitudeI*1e-7,p.longitude!==undefined ? p.longitude : p.longitudeI*1e-7);}}} }
            MenuItem { text: app.tr("This computer"); onTriggered: app.act("locate_host") }
        } }
        MeshButton { text: app ? app.tr("Map settings") : "Map settings"; onClicked: app.go("Preferences") }
        MeshButton { text: app.tr("View"); onClicked: viewPopup.open(); Popup {
            id: viewPopup; objectName: "mapViewPopup"; width: 250; height: viewOptions.implicitHeight+24; padding: 12; margins: 8;
            background: Rectangle { color: app.panel; radius: 7; border.color: app.muted } closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
            ColumnLayout {
                id: viewOptions; anchors.fill: parent
                Label { textFormat: Text.PlainText; text: app.tr("Rotation") }
                Slider { id: bearing; from: 0; to: 360; Layout.fillWidth: true; onMoved: map.setView(value,pitch.value) }
                Label { textFormat: Text.PlainText; text: app.tr("Tilt") }
                Slider { id: pitch; from: 0; to: 45; Layout.fillWidth: true; onMoved: map.setView(bearing.value,value) }
                MeshButton { text: app.tr("Reset view"); onClicked: {bearing.value=0;pitch.value=0;map.setView(0,0);} }
            }
        } }
    }
    Column {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 20; anchors.bottomMargin: 45
        MeshButton { text: "+"; width: 48; onClicked: map.changeZoom(1) }
        MeshButton { text: "−"; width: 48; onClicked: map.changeZoom(-1) }
    }
    MeshDialog {
        id: waypointDialog; objectName: "waypointDialog"
        title: app ? app.tr("Map position") : "Map position"; modal: true; anchors.centerIn: parent
        implicitWidth: 460; implicitHeight: 520
        width: Math.min(parent.width-30,implicitWidth); height: Math.min(parent.height-20,implicitHeight)
        standardButtons: Dialog.Close
        contentItem: ScrollView {
            id: waypointScroll; implicitWidth: 0; implicitHeight: 0; contentWidth: availableWidth; clip: true
            ColumnLayout {
                width: waypointScroll.availableWidth
            Label { textFormat: Text.PlainText; text: app ? app.tr("Create a waypoint or set your radio's fixed position.") : "Create a waypoint or set your radio's fixed position."; wrapMode: Text.Wrap; Layout.fillWidth: true }
            TextField { id: latitude; Layout.fillWidth: true; placeholderText: app ? app.tr("Latitude") : "Latitude" }
            TextField { id: longitude; Layout.fillWidth: true; placeholderText: app ? app.tr("Longitude") : "Longitude" }
            TextField { id: name; Layout.fillWidth: true; placeholderText: app ? app.tr("Waypoint name") : "Waypoint name" }
            TextField { id: description; Layout.fillWidth: true; placeholderText: app ? app.tr("Description") : "Description" }
            SpinBox { id: lifetime; from: 1; to: 168; value: 24; editable: true; ToolTip.text: app ? app.tr("Expires after this many hours") : "Expires after this many hours"; ToolTip.visible: hovered }
            MeshButton { text: app ? app.tr("Broadcast waypoint") : "Broadcast waypoint"; enabled: app && app.s.connected && name.text.length>0; onClicked: {
                app.ask("Broadcast this waypoint","command",{name:"waypoint",args:{channel:app.s.channel,waypoint:{id:Math.floor(Math.random()*4294967294)+1,name:name.text,description:description.text,latitude_i:Math.round(Number(latitude.text)*1e7),longitude_i:Math.round(Number(longitude.text)*1e7),expire:Math.floor(Date.now()/1000)+lifetime.value*3600}}});waypointDialog.close();
            } }
            MeshButton { text: app ? app.tr("Set radio position here") : "Set radio position here"; enabled: app && app.s.connected; onClicked: {app.ask("Set the radio's fixed position","command",{name:"fixed_position",args:{latitude:latitude.text,longitude:longitude.text}});waypointDialog.close();} }
            }
        }
    }
}
