#!/bin/bash

echo 'Welcome to the setup script for Bubble Robotics'
echo 'This script will prompt you to give some information then will configure the BlueRov2 to work with the bubble_blue software'
echo 'First, checking wifi...'

#Check if wifi is connected to internet.
if ! ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then
    echo "No internet connection detected. Please connect to Wi-Fi first using the GUI from the command: "
    echo "              sudo nmtui                  "
    echo "and rerun the setup script after the wifi is connected. Thanks!"
    exit 1
fi


if [ -f "bubble_ascii.txt" ]; then
    echo "Not re-importing bubble logo art"
else
    wget https://raw.githubusercontent.com/radam1/bubble_setup/refs/heads/main/bubble_ascii.txt
    echo 'echo -e "\033[34m$(cat bubble_ascii.txt)\033[0m"' >> ~/.bashrc
fi

echo -e "\033[34m$(cat bubble_ascii.txt)\033[0m"

# Check the ownership of docker and, if it's owned by the root user then switch it to the pi user

# Check if CR_PAT is already in .bashrc.
# if it isnt, ask for one and put it in .bashrc,
# if it is, ask if it should be replaced
if ! grep -q "export CR_PAT=" ~/.bashrc; then
    echo "No token available in .bashrc"
    read -p "Enter your Github Username: " username
    read -p "Enter your GitHub Classic Token Key: " token
    echo
    if [ -z "$token" ]; then
        echo "Error: No token provided."
        exit 1
    fi
    echo "export CR_PAT=\"$token\"" >> ~/.bashrc
    echo "Added CR_PAT to ~/.bashrc"

    # Log in to GitHub Container Registry
    echo "$token" | docker login ghcr.io -u "$username" --password-stdin

else
    # Update the value if it already exists
    echo "CR_PAT Exists in .bashrc"
    read -p "Would you like to replace token in .bashrc? (y/n) " answer
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        read -p "Enter your Github Username: " username
        read -p "Enter your GitHub Classic Token Key: " token
        echo
        if [ -z "$token" ] || [ -z "$username" ]; then
            echo "Error: No token provided."
            exit 1
        fi
        sed -i.bak "s|^export CR_PAT=.*|export CR_PAT=\"$token\"|" ~/.bashrc
        echo "Updated CR_PAT in ~/.bashrc. Logging into docker..."
	echo "$token" | docker login ghcr.io -u "$username" --password-stdin
    elif [[ "$answer" == "n" || "$answer" == "N" ]]; then
    	echo "Not updating existing CR_PAT. Logging into docker..."
        source ~/.bashrc
        read -p "Enter your Github Username: " username
        echo "$CR_PAT" | docker login ghcr.io -u "$username" --password-stdin
    else
    	echo "Invalid Choice. Shutting down script"
	exit 1
    fi
fi

# installing some debugging tools
echo "Installing packages for debugging and configuration..."
sudo apt update
sudo apt install minicom tcpdump python3-numpy python3-serial -y 

# install or update the most recent robot docker image
docker pull ghcr.io/patpat98/bubble_blue:jazzy-robot

# Adding a few aliases to the .bashrc file
if ! grep -q "alias enter_bb" ~/.bashrc; then
    echo "alias enter_bb=\"docker exec -it bubble_blue /bin/bash\"" >> ~/.bashrc
fi

# Add the docker compose script
if ! [ -f docker-compose.yaml ]; then 
    wget https://raw.githubusercontent.com/radam1/bubble_setup/refs/heads/main/docker-compose.yaml
fi

# Finally, check to see if we want to do the VN100 HSI right now

# if it doesn't exist, pull HSI Estimator script
if ! [ -f VN100_HSIEstimator.py ]; then
    wget https://raw.githubusercontent.com/radam1/bubble_setup/refs/heads/main/VN100_HSIEstimator.py
fi 

# check if we want to run it now
read -p "Would you like to run the Vectornav VN100 Hard/Soft Iron Calibration right now? (y/n) " answer_hsi
if [ "$answer_hsi" == "y" || "$answer_hsi" == "Y" ]; then
    python3 VN100_HSIEstimator.py
elif [ "$answer_hsi" == "n" || "$answer_hsi" == "N" ]; then
    echo "Not running the HSI Estimator Script. If you'd like to run it later, use the command: "
    echo "--------------------------------------------"
    echo "        python3 VN100_HSIEstimator.py       "
    echo "--------------------------------------------"
else
    echo "Invalid Choice! Shutting Down Setup..." 
    exit 1 
fi

exit 0 