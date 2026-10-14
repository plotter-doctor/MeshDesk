"""Stable Qt rows keep focused editors alive during background radio updates."""
from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt


class FieldModel(QAbstractListModel):
    ROLE = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def roleNames(self):
        return {self.ROLE: b'fieldData'}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if role == self.ROLE and index.isValid() and 0 <= index.row() < len(self.rows):
            return self.rows[index.row()]

    def sync(self, rows):
        if [r['path'] for r in rows] != [r['path'] for r in self.rows]:
            self.beginResetModel()
            self.rows = rows
            self.endResetModel()
        else:
            for i, row in enumerate(rows):
                if self.rows[i] != row:
                    self.rows[i] = row
                    self.dataChanged.emit(self.index(i), self.index(i), [self.ROLE])
