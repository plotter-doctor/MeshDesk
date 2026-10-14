import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15

Dialog {
    id: dialog
    // Material's elevation effect does not draw reliably with Qt 5's
    // software scene graph. Keep the actual dialog surface opaque.
    background: Rectangle { color: dialog.Material.background; radius: 10 }
    Overlay.modal: Rectangle { color: "#99000000" }
}
