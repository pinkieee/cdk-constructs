# Library of CDK constructs

- Pull Request Validator (based on [AWS blog](https://aws.amazon.com/blogs/devops/validating-aws-codecommit-pull-requests-with-aws-codebuild-and-aws-lambda/))

# How to build with Poetry

To build a new version:
1. make sure that any dependencies have been added to poetry with:

```
poetry add <package_name>
```


2. Bump the version number in `pyproject.toml`

3. Run 
```
poetry build
```
4. Your `.whl` package is located in `/dist`

# How to Use

When you have a build, you can install the package with:

`pip install cdk_constructs-0.2.0-py3-none-any.whl`

Now you can use the object PullRequestValidator() in your CDK app by importing the module in the CDK stack and constructing the object.

```
from aws_cdk import core
from cdk_constructs.validate_pull_requests import PullRequestValidator


class AppStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here

        PullRequestValidator(
            self, "PRValidator",
            repo_name="repository-name",
            buildspec_file="deploy/buildspec.yaml")
```

The `buildspec.yaml` file will include what you want to have run to validate if the PR is adhering to your standards. 

Example `buildspec.yaml`:

```
version: 0.2
  phases:
    install:
      commands:
        - pip install pre-commit
        - pre-commit install
    build:
      commands:
        - pre-commit run --all-files
artifacts:
  files:
    - *
```