import QtQuick 2.15
import QtQuick.VirtualKeyboard 2.15

Item {
    id: keyboardContainer
    property alias active: panel.active
    implicitHeight: panel.implicitHeight
    InputPanel {
        id: panel
        objectName: "touchKeyboard"
        parent: keyboardContainer
        width: parent.width
        anchors.bottom: parent.bottom
        z: 90
        visible: active
    }
}
