# Developer instructions

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

## ..create a pull request build

After every push in an open pr, if all validations pass, a test image is released on https://gallery.ecr.aws/vdb-public/gh-mpyl. 


## ..code style

We use the [black formatter](https://black.readthedocs.io/en/stable/getting_started.html) in our codebase.
Check the instructions on how to set it up for your IDE [here](https://black.readthedocs.io/en/stable/integrations/editors.html).

## ..create a new release

Releases are created automatically by the CI/CD pipeline based on [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/).


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
