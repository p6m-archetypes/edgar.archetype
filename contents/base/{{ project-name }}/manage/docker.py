import subprocess


def docker_build():
    print("Creating docker image")
    subprocess.run(["docker", "build", "-t", "{{ project-name }}", "."])
