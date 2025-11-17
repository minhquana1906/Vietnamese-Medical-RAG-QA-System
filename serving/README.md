# Installing Docker
## Installation

1. Setup the Docker repository:

```bash
# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
```

2. Install the Docker packages:
```bash
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

> Note
> The Docker service starts automatically after installation. To verify that Docker is running, use:
 ```sudo systemctl status docker```
> Some systems may have this behavior disabled and will require a manual start:
```sudo systemctl start docker```


# Installing the NVIDIA Container Toolkit
## Installation
### Prerequisites
1. Read this section about platform support.

2. Install the NVIDIA GPU driver for your Linux distribution. NVIDIA recommends installing the driver by using the package manager for your distribution. For information about installing the driver with a package manager, refer to the NVIDIA Driver Installation Quickstart Guide. Alternatively, you can install the driver by downloading a .run installer.

>Note
>There is a known issue on systems where systemd cgroup drivers are used that cause containers to lose access to requested GPUs when systemctl daemon reload is run. Refer to the troubleshooting documentation for more information.

### With apt: Ubuntu, Debian

>Note
>These instructions should work for any Debian-derived distribution.

1. Install the prerequisites for the instructions below:

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends \
curl \
gnupg2
```

2. Configure the production repository:
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

Optionally, configure the repository to use experimental packages:

```bash
sudo sed -i -e '/experimental/ s/^#//g' /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

3. Update the packages list from the repository:

```bash
sudo apt-get update
```

4. Install the NVIDIA Container Toolkit packages:
```bash
export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.18.0-1
sudo apt-get install -y \
    nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
```

## Configuration
### Prerequisites
- You installed a supported container engine (Docker, Containerd, CRI-O, Podman).
- You installed the NVIDIA Container Toolkit.

### Configuring Docker
1. Configure the container runtime by using the nvidia-ctk command:
```bash
sudo nvidia-ctk runtime configure --runtime=docker
```
The nvidia-ctk command modifies the /etc/docker/daemon.json file on the host. The file is updated so that Docker can use the NVIDIA Container Runtime.

2. Restart the Docker daemon:
```bash
sudo systemctl restart docker
```

### Rootless mode
To configure the container runtime for Docker running in Rootless mode, follow these steps:

1. Configure the container runtime by using the nvidia-ctk command:

```bash
nvidia-ctk runtime configure --runtime=docker --config=$HOME/.config/docker/daemon.json
```

2. Restart the Rootless Docker daemon:

```bash
systemctl --user restart docker
```

3. Configure /etc/nvidia-container-runtime/config.toml by using the sudo nvidia-ctk command:

```bash
sudo nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place
```

## Test
```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

or
```bash
sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```


