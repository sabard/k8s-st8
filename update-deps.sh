#!/bin/bash
set -e

cd "$(dirname "$0")" # script always runs from install directory

eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv activate k8s-st8

pip install --upgrade pip setuptools wheel pip-tools

pip-compile "./requirements.in" 
pip-compile "./requirements-dev.in"
pip-sync "./requirements-dev.txt"
pip install --no-deps --editable .