#!/bin/bash
set -ev

# install pyenv
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
if [ ! "$(pyenv --version)" ] ; then
    curl https://pyenv.run | bash
    source "$(dirname "$0")/pyenv_config.sh"
fi

pyenv install 3.13.18 -s
if [ "$(pyenv version-name)" != "k8s-st8" ]; then
    pyenv virtualenv 3.13.18 k8s-st8
fi

"$(dirname "$0")/update-deps.sh"