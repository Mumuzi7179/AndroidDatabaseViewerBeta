# -*- coding: utf-8 -*-
"""
SQLCipher3 解密参数输入对话框
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QPushButton
)
from PySide6.QtCore import Qt


class Cipher3Dialog(QDialog):
    """用于输入密码及SQLCipher3参数的对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("解密 SQLCipher 数据库")
        self.setModal(True)
        self.resize(420, 220)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Cipher 版本选择
        self.cipher_version_combo = QComboBox()
        self.cipher_version_combo.addItems(["v3", "v4"])  # 默认 v3

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(512, 8192)
        self.page_size_spin.setValue(1024)
        self.kdf_iter_spin = QSpinBox()
        self.kdf_iter_spin.setRange(1, 1000000)
        self.kdf_iter_spin.setValue(64000)
        self.hmac_combo = QComboBox()
        self.hmac_combo.addItems(["SHA1", "SHA256", "SHA512"])
        self.kdf_combo = QComboBox()
        self.kdf_combo.addItems(["SHA1", "SHA256", "SHA512"])

        layout = QVBoxLayout(self)

        # Cipher 版本
        row = QHBoxLayout()
        row.addWidget(QLabel("Cipher版本:"))
        row.addWidget(self.cipher_version_combo)
        layout.addLayout(row)

        # 密码
        row = QHBoxLayout()
        row.addWidget(QLabel("密码:"))
        row.addWidget(self.password_edit)
        layout.addLayout(row)

        # 页大小
        row = QHBoxLayout()
        row.addWidget(QLabel("页大小:"))
        row.addWidget(self.page_size_spin)
        layout.addLayout(row)

        # KDF迭代次数
        row = QHBoxLayout()
        row.addWidget(QLabel("KDF迭代次数:"))
        row.addWidget(self.kdf_iter_spin)
        layout.addLayout(row)

        # HMAC算法
        row = QHBoxLayout()
        row.addWidget(QLabel("HMAC算法:"))
        row.addWidget(self.hmac_combo)
        layout.addLayout(row)

        # KDF算法
        row = QHBoxLayout()
        row.addWidget(QLabel("KDF迭代算法:"))
        row.addWidget(self.kdf_combo)
        layout.addLayout(row)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("解密")
        cancel_btn = QPushButton("取消")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_params(self):
        """返回输入的参数"""
        return {
            'password': self.password_edit.text(),
            'cipher_version': self.cipher_version_combo.currentText(),
            'page_size': int(self.page_size_spin.value()),
            'kdf_iter': int(self.kdf_iter_spin.value()),
            'hmac_alg': self.hmac_combo.currentText(),
            'kdf_alg': self.kdf_combo.currentText(),
        }