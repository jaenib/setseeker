# launcher.sh
source setseek_venv/bin/activate
python fileshazzer.py "$@"
if [ $? -ne 0 ]; then
    echo "An error occurred while running the script."
    exit 1
fi
echo "fileshazzer shazzed successfully. Moving on to seekspawner..."
python seekspawner.py "$@"
if [ $? -ne 0 ]; then
    echo "An error occurred while running the script."
    exit 1
fi
echo "seekspawner spawned successfully. Enjoy the spoils"