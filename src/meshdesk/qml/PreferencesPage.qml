import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ScrollView {
    id: view; property var app; contentWidth: availableWidth; clip: true
    ColumnLayout {
        width: parent.width; spacing: 14
        Item { height: 5 }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Preferences") : "Preferences"; font.pixelSize: 25; font.bold: true; Layout.leftMargin: 22 }
        ColumnLayout {
            Layout.fillWidth: true; Layout.margins: 22; spacing: 14
            MeshComboBox { model: [app.tr("Dark"),app.tr("Light"),app.tr("Automatic")]; currentIndex: ["dark","light","system"].indexOf(app.s.theme_preference); onActivated: app.act("preference",{key:"theme",value:["dark","light","system"][currentIndex]}) }
            Switch { text: app ? app.tr("12-hour clock") : "12-hour clock"; checked: app && app.s.clock12; onToggled: app.act("preference",{key:"clock12",value:checked}) }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Language") : "Language"; font.bold: true }
            MeshComboBox {
                model: app ? app.s.languages : []; textRole: "name"
                currentIndex: {if(!app)return 0;for(var i=0;i<app.s.languages.length;i++)if(app.s.languages[i].code===app.s.language)return i;return 0;}
                onActivated: app.act("preference",{key:"language",value:app.s.languages[currentIndex].code})
            }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Maps") : "Maps"; font.pixelSize: 21; font.bold: true }
            Switch { text: app ? app.tr("Download map tiles") : "Download map tiles"; checked: app && app.s.online_maps; onToggled: app.act("preference",{key:"online_maps",value:checked}) }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Map tiles use an internet connection. The cache is limited to 50 MB. Node positions are drawn locally.") : "Map tiles use an internet connection. The cache is limited to 50 MB. Node positions are drawn locally."; wrapMode: Text.Wrap; Layout.fillWidth: true; color: app ? app.muted : "gray" }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Raster tile URL") : "Raster tile URL"; font.bold: true }
            TextField { Layout.fillWidth: true; text: app ? app.s.tile_url : ""; selectByMouse: true; placeholderText: app ? app.tr("https://…/{z}/{x}/{y}.png") : "https://…/{z}/{x}/{y}.png"; onEditingFinished: app.act("preference",{key:"tile_url",value:text}) }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Map attribution") : "Map attribution"; font.bold: true }
            TextField { Layout.fillWidth: true; text: app ? app.s.tile_attribution : ""; selectByMouse: true; onEditingFinished: app.act("preference",{key:"tile_attribution",value:text}) }
            Label { textFormat: Text.PlainText; text: app ? app.tr("Official releases") : "Official releases"; font.pixelSize: 21; font.bold: true; topPadding: 12 }
            MeshButton { text: app ? app.tr("Check official releases") : "Check official releases"; enabled: app && !app.s.busy; onClicked: {app.act("check_updates");app.go("Activity");} }
            Label { textFormat: Text.PlainText; text: "MeshDesk " + (app ? app.s.version : "") + " · native Qt interface\nOfficial Meshtastic Python library · GPL-3.0"; wrapMode: Text.Wrap; Layout.fillWidth: true; color: app ? app.muted : "gray"; topPadding: 20 }
        }
    }
}
