# Developer instructions

You can work on MPyL in one of two ways:

# 🧪 _experimental:_ using Devcontainers

1. install [DevPod](https://devpod.sh/)
   ```
   brew install --cask devpod
   ```
2. start a new workspace
   ```
   devpod up git@github.com:Vandebron/gh-mpyl.git --id mpyl --ide openvscode
   ```

A new browser window will open with the workspace ready to be worked on 🚀


### IntelliJ configuration
If you prefer to use a JetBrains IDE, first install [JetBrains Gateway](https://www.jetbrains.com/remote-development/gateway/) and then run:
```
devpod up mpyl --ide intellij
```
You might have to install the [IntelliJ Python plugin](https://plugins.jetbrains.com/plugin/631-python) before being able to work on Python code. If you do, then you'll also need to link to the pre-installed Python interpreter by:
1. open the _Project Structure_ menu
2. in _Platform Settings_ → _SDKs_ add a new SDK using _Add Python SDK from disk…_
3. select _Virtualenv Environment_
4. Choose _Existing environment_ and use `/root/.local/share/virtualenvs/gh-mpyl/bin/python3.13` as the path to the interpreter

Yes, Python is a PITA 😩. We're hoping to further pre-configure this as soon as IntelliJ supports it.

If you have a PyCharm license this is all probably pre-configured for you. You can use it with:
```
devpod up mpyl --ide pycharm
```


### SSH into the container
If you're more comfortable in a black and white terminal, then you can also just ssh into the container by running:
```
devpod ssh mpyl
```
or just simply:
```
ssh mpyl.devpod
```


# 🕰️ _stable_: installing everything locally

## ..install mpyl for development

1. Clone the mpyl repo
 ```shell
 gh repo clone Vandebron/gh-mpyl
 ```

2. Install dependencies
 ```shell
 pipenv install -d
 ```

## ..run tests and checks

To run linting (`pylint`), type checking (`mypy`) and testing (`pytest`) in one go, run:

```shell
pipenv run validate
```

## ..code style

We use the [black formatter](https://black.readthedocs.io/en/stable/getting_started.html) in our codebase.
Check the instructions on how to set it up for your
IDE [here](https://black.readthedocs.io/en/stable/integrations/editors.html).

## ..troubleshoot Python setup

1. Check if you're in the correct `venv`
   To check this, run first:
    ```shell
    pipenv shell
    ```
   Then check if the correct virtual environment (named `pympl`) is launched.
2. Check your `bashrc` (or `zshrc`) if you have any overrides of environmental variables like `PIPENV_PIPFILE`. If so,
   remove those, source your bash config and try Step 1. again
3. To see if everything is running as intended, execute
    ```shell
    pipenv run test
    ```
   which should now succeed.


## ..running the mpyl sourcecode against another repository

For a shorter feedback loop, you can run the mpyl sourcecode against another repository.
To test the mpyl sourcecode against the peculiarities of your own repository, you can run the following command:

```shell
PIPENV_PIPFILE=/<absolute_path_to_mpyl_repo>/Pipfile pipenv run cli-ext build status
```
Assign PIPENV_PIPFILE to the absolute path of your Pipfile and run the command.
⚠️Note that an `.env` file needs to be present in the root if this repository, containing the following variable:

```shell
PYTHONPATH=/<absolute_path_to_mpyl_repo>/src
```


# Commit messages and versioning
This repository adheres to the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.
While you do not have to follow it for every commit, at least **the title of your pull request must follow this convention**.

Once your pull request is merged, a new version of this project will be automatically released.

If the changes in your pull request require upstream modifications, **its title must be marked as [breaking](https://www.conventionalcommits.org/en/v1.0.0/#commit-message-with--to-draw-attention-to-breaking-change)** to clearly indicate to other developers that it cannot be automatically upgraded in any of our repositories.
