# 🖐️ Usage

## ..MPyL CLI

### Suggested first time use

#### 1. Run MPyL

There are multiple ways to run gh-mpyl:

1. Build a local image based on the [Dockerfile](./Dockerfile).
    ```shell
    docker build -t gh-mpyl .
    docker run gh-mpyl -v $(pwd):/repo health
    ```
    The run command should be run from the calling repository.
2.  Run a dockerfile from the [gh-mpyl dockerhub](https://hub.docker.com/r/vdbpublic/gh-mpyl).
    ```shell
    docker run -v $(pwd):/repo vdbpublic/gh-mpyl:pr-1 health
    ```
3. Directly from the source code, see [Developer instructions](./README-dev.md).

Validations are automatically triggered in pr's. You can quickly validate your local code by running
```shell
pipenv run validate
```


### Command structure

Top level commands options are passed on to sub commands and need to be specified *before* the sub command.
In ```mpyl build --config <path> list ```, the `--config` option applies to all `build` commands, like `run`
or `status`.

##### MPyL configuration

MPyL can be configured through a file that adheres to the `mpyl_config.yml`
[schema](https://vandebron.github.io/mpyl/schema/mpyl_config.schema.yml).
Which configuration fields need to be set depends on your use case. The error messages that you
encounter while using the cli may guide you through the process.
Note that the included `mpyl_config.example.yml` is just an example.

Secrets can be injected
through environment variable substitution via the
[pyaml-env](https://github.com/mkaranasou/pyaml_env) library.
Note that values for which the ENV variable is not set,
will be absent in the resulting configuration dictionary.
<details>
  <summary>Example config</summary>
```yaml
.. include:: mpyl_config.example.yml
```
</details>

Check the [schema](https://vandebron.github.io/mpyl/schema/run_properties.schema.yml) for `run_properties.yml`, which contains detailed
documentation and can be used to enable on-the-fly validation and auto-completion in your IDE.

###### Stage configuration

MPyL can be configured to use an arbitrary set of build stages. Typical CI/CD stages are `build`, `test` or `deploy`.
See `mpyl.steps` for the steps that come bundled and how to define and register your own.

<details>
  <summary>Example stage configuration</summary>
```yaml
.. include:: mpyl_stages.schema.yml
```
</details>

#### Auto completion
Usability of the CLI is *greatly enhanced* by autocompletion.
To enable autocompletion, depending on your terminal, do the following:

###### Bash
Add this to ``~/.bashrc``:
```shell
eval "$(_MPYL_COMPLETE=bash_source mpyl)"
```
###### Zsh
Add this to ``~/.zshrc``:
```shell
eval "$(_MPYL_COMPLETE=zsh_source mpyl)"
```
###### Fish
Add this to ``~/.config/fish/completions/foo-bar.fish``:
```shell
eval (env _MPYL_COMPLETE=fish_source mpyl)
```

###### Intellij IDEA or PyCharm
Go to: `Preferences | Languages & Frameworks | Schemas and DTDs | JSON Schema Mappings`
- Add new schema
- Add matching schema file from latest release:
  - */deployment/project.yml -> https://vandebron.github.io/mpyl/schema/project.schema.yml
  - mpyl_config.example.yml -> https://vandebron.github.io/mpyl/schema/mpyl_config.schema.yml
  - run_properties.yml -> https://vandebron.github.io/mpyl/schema/run_properties.schema.yml
- Select version: ``JSON Schema Version 7``
- Add YAML files corresponding to the schema or add the file pattern. (For instance, adding the file pattern `project.yml` to the `project.schema.yml` will take care of autocompletion in any `project.yml`.)


## ..defining projects

### File structure

All CI/CD related files reside in a `./deployment` sub folder, relative to the project source code folder.
A typical deployment folder may contain the following files

```shell
├── Dockerfile-mpl
├── project.yml
└── docker-compose-test.yml
```

### project.yml

The `project.yml` defines which steps needs to be executed during the CI/CD process.

```yaml
name: batterypackApi
stages:
  build: Sbt Build
  test: Sbt Test
  deploy: Kubernetes Deploy
```

- `name` is a required parameter
- `stages` are optional parameters. Stages that are undefined will be skipped. Depending on the
  type of project you want to build, you need to specify an appropriate action to be performed in each stage.
  For example: `Sbt Build` can be used for scala projects, and `Docker Build` can be used for front-end projects.
- `kubernetes` is a required parameter if `deploy` stage is set to `Kubernetes Deploy`.

The [schema](https://vandebron.github.io/mpyl/schema/project.schema.yml) for `project.yml` contains detailed
documentation and
can be used to enable on-the-fly validation and auto-completion in your IDE.

#### Artifacts

MPyL's artifact metadata is stored in the hidden `.mpyl` folders next to `project.yml`.
These folders are used to cache information about (intermediate) build results.
A typical `.mpyl` folder has a file for each executed stage. The `BUILD.yml` file contains the metadata for the
build step. For example:
```yaml
message: Pushed ghcr.io/samtheisens/nodeservice:pr-6
```
These files speed up subsequent runs by preventing steps from being executed when their inputs have not changed.

🧹 These `.mpyl` folders can be safely deleted to force a full rebuild via
```shell
mpyl build clean
```

## ..create a custom step

See `mpyl.steps`.
