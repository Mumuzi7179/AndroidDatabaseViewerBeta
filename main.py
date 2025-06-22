#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android数据库可视化工具 - 主程序入口
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from src.gui.main_window import MainWindow

def main():
    """主程序入口"""
    app = QApplication(sys.argv)
    app.setApplicationName("Android数据库可视化工具")
    app.setApplicationVersion("1.0.0")
    
    # 设置应用图标和样式
    app.setStyle("Fusion")
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    return app.exec()

if __name__ == "__main__":
    sys.exit(main()) 