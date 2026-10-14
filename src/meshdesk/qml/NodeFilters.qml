import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

MeshDialog {
    id: view; objectName: "nodeFiltersDialog"; property var app
    title: app.tr("Filter nodes"); modal: true; anchors.centerIn: parent; width: Math.min(parent.width-20,560); height: Math.min(parent.height-20,500)
    standardButtons: Dialog.Close
    contentItem: ScrollView {
        id: filtersScroll; implicitWidth: 520; implicitHeight: 400
        contentWidth: availableWidth; clip: true
        ColumnLayout {
            width: filtersScroll.availableWidth; spacing: 10
            MeshButton { text: app.tr("Reset filters"); onClicked: app.act("node_filters",{reset:true}) }
            Repeater {
                model: [{key:"favorite",name:"Favorites"},{key:"mqtt",name:"Via MQTT"},{key:"ignored",name:"Ignored"},{key:"unheard",name:"Never heard"},{key:"unknown_hops",name:"Unknown hops"}]
                delegate: RowLayout {
                    Layout.fillWidth: true
                    Label { textFormat: Text.PlainText; text: app.tr(modelData.name); Layout.fillWidth: true }
                    MeshComboBox { model: [app.tr("Any"),app.tr("Yes"),app.tr("No")]; currentIndex: app.s.node_filters[modelData.key] === undefined ? 0 : app.s.node_filters[modelData.key] ? 1 : 2; onActivated: app.act("node_filters",{key:modelData.key,value:currentIndex===0 ? null : currentIndex===1}) }
                }
            }
            Repeater {
                model: app ? app.s.filter_ranges : []
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    Label { textFormat: Text.PlainText; text: app.tr(modelData.name); font.bold: true }
                    RowLayout {
                        TextField { Layout.fillWidth: true; placeholderText: app.tr("Minimum"); text: app.s.node_filters[modelData.key+"_min"] || ""; onEditingFinished: app.act("node_filters",{key:modelData.key+"_min",value:text}) }
                        TextField { Layout.fillWidth: true; placeholderText: app.tr("Maximum"); text: app.s.node_filters[modelData.key+"_max"] || ""; onEditingFinished: app.act("node_filters",{key:modelData.key+"_max",value:text}) }
                    }
                }
            }
            EnumFilter { app: view.app; filterKey: "roles"; title: app.tr("Role") }
            EnumFilter { app: view.app; filterKey: "hardware"; title: app.tr("Hardware") }
        }
    }
}
