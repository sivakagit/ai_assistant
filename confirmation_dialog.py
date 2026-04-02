from PySide6.QtWidgets import QMessageBox


def confirm_action(parent, message: str) -> bool:
    """
    Show a Yes/No confirmation dialog.

    Parameters
    ----------
    parent  : QWidget  – parent window (can be None)
    message : str      – question to display

    Returns
    -------
    bool – True if the user clicked Yes, False otherwise
    """
    reply = QMessageBox.question(
        parent,
        "Confirm Action",
        message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No           # default to No (safer for destructive actions)
    )

    return reply == QMessageBox.Yes