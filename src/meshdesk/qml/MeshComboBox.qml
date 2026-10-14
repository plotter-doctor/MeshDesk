import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Window 2.15

ComboBox {
    id: control
    hoverEnabled: true
    leftPadding: 12; rightPadding: 32
    background: Rectangle {
        implicitWidth: 190; implicitHeight: 44; radius: 7
        color: control.down ? (control.Material.theme===Material.Dark ? "#365260" : "#d1e1e5") : control.Material.background
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? "#62dcb0" : "#67818c"
    }
    contentItem: Text {
        text: control.displayText; font: control.font; color: control.Material.foreground
        textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
    }
    delegate: ItemDelegate {
        width: control.width; height: 46
        text: control.textAt(index); highlighted: control.highlightedIndex===index
        contentItem: Text { text: parent.text; font: control.font; color: control.Material.foreground; textFormat: Text.PlainText; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: parent.down ? "#398c73" : parent.highlighted ? (control.Material.theme===Material.Dark ? "#365260" : "#d1e1e5") : control.Material.background }
    }
    popup: Popup {
        objectName: control.objectName+"Popup"
        y: control.height+4; width: control.width; padding: 4; margins: 8
        height: Math.min(contentItem.implicitHeight+8,300,control.Window.height-90)
        background: Rectangle { color: control.Material.background; radius: 7; border.color: "#67818c" }
        contentItem: ListView {
            clip: true; implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar {}
        }
    }
}
