import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15

ToolButton {
    id: control
    hoverEnabled: true
    topInset: 0; bottomInset: 0
    background: Rectangle {
        implicitWidth: 42; implicitHeight: 42; radius: 7
        color: control.down ? "#398c73" : control.hovered ? (control.Material.theme===Material.Dark ? "#365260" : "#d1e1e5") :
               (control.Material.theme===Material.Dark ? "#243b47" : "#e2ecef")
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? "#62dcb0" : (control.Material.theme===Material.Dark ? "#486270" : "#9db3bd")
        opacity: control.enabled ? 1 : 0.4
    }
}
