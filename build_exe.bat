@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Building executable...
pyinstaller --onefile --windowed stock_app.py

echo Done! The exe is in dist\stock_app.exe
pause