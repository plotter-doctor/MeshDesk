import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15

Button {
    id: control
    hoverEnabled: true
    topInset: 0; bottomInset: 0
    leftPadding: 14; rightPadding: 14
    background: Rectangle {
        implicitWidth: 90; implicitHeight: 44; radius: 7
        color: !control.enabled ? (control.Material.theme===Material.Dark ? "#26343b" : "#e1e5e7") :
               control.down ? "#398c73" : control.highlighted || control.checked ? "#62dcb0" :
               control.hovered ? (control.Material.theme===Material.Dark ? "#365260" : "#d1e1e5") :
               (control.Material.theme===Material.Dark ? "#29414d" : "#e2ecef")
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? "#62dcb0" : (control.Material.theme===Material.Dark ? "#486270" : "#9db3bd")
    }
    contentItem: Text {
        text: control.text; font: control.font; textFormat: Text.PlainText
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
        color: !control.enabled ? "#798d96" : control.highlighted || control.checked || control.down ? "#10232a" : control.Material.foreground
    }
}
