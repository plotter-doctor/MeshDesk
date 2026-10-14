import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ColumnLayout {
    id: view
    property var app
    property string filterKey
    property string title
    property var selected: (app.s.node_filters[filterKey] || "").split(",").filter(function(s){return s.length>0;})
    Layout.fillWidth: true
    Label { textFormat: Text.PlainText; text: view.title; font.bold: true }
    MeshButton {
        Layout.fillWidth: true
        text: view.selected.length ? view.selected.join(", ") : app.tr("Any")
        onClicked: choices.open()
    }
    MeshDialog {
        id: choices; objectName: view.filterKey+"FilterDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(parent.width-30,480); height: Math.min(parent.height-30,460)
        title: view.title; modal: true; standardButtons: Dialog.Close
        ColumnLayout {
            anchors.fill: parent
            TextField { id: search; placeholderText: app.tr("Search"); Layout.fillWidth: true }
            MeshButton { text: app.tr("Clear"); onClicked: app.act("node_filters",{key:view.filterKey,value:""}) }
            ListView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: app.s.filter_enums[view.filterKey].filter(function(s){return s.toLowerCase().indexOf(search.text.toLowerCase())>=0;})
                delegate: CheckBox {
                    width: ListView.view.width; text: modelData; checked: view.selected.indexOf(modelData)>=0
                    onToggled: {
                        var values=view.selected.slice();var i=values.indexOf(modelData);
                        if(checked && i<0)values.push(modelData);else if(!checked && i>=0)values.splice(i,1);
                        app.act("node_filters",{key:view.filterKey,value:values.join(",")});
                    }
                }
                ScrollBar.vertical: ScrollBar {}
            }
        }
    }
}
