from aws_cdk import (
    aws_codebuild as codebuild,
    aws_codecommit as codecommit,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda,
    core,
)


class PullRequestValidator(core.Construct):
    """Validate Codecommit pull requests with Codebuild and comment on PR with status.

    Based on aws blog "Validating AWS CodeCommit Pull Requests with AWS CodeBuild and AWS Lambda".
    https://aws.amazon.com/blogs/devops/validating-aws-codecommit-pull-requests-with-aws-codebuild-and-aws-lambda/

    Parameters
    ----------
    core : [type]
        [description]
    """

    def __init__(self, scope: core.Construct, id: str, repo_name: str, buildspec_file: str) -> None:
        super().__init__(scope, id)

        repo = codecommit.Repository.from_repository_name(
            self, "ImportedRepo", repo_name
        )

        self.codebuild_project = codebuild.PipelineProject(
            self,
            "CodebuildProject",
            build_spec=codebuild.BuildSpec.from_source_filename(buildspec_file)
        )

        # Cloudwatch Event Rule on Pull Request state change in repository
        on_pull_request_rule = repo.on_pull_request_state_change(
            "OnPullRequestChange", rule_name=f"pull-request-event-{ repo_name }"
        )

        # Codebuild project to run on Cloudwatch Event Rule trigger
        # Pass the commit hash, pull request id, repo name,
        # source hash and destination hash to Codebuild
        on_pull_request_rule.add_target(
            targets.CodeBuildProject(
                project=self.codebuild_project,
                event=events.RuleTargetInput.from_object(
                    dict(
                        sourceVersion=events.EventField.from_path(
                            "$.detail.sourceCommit"
                        ),
                        environmentVariablesOverride=[
                            dict(
                                name="pullRequestId",
                                value=events.EventField.from_path(
                                    "$.detail.pullRequestId"
                                ),
                                type="PLAINTEXT",
                            ),
                            dict(
                                name="repositoryName",
                                value=events.EventField.from_path(
                                    "$.detail.repositoryNames[0]"
                                ),
                                type="PLAINTEXT",
                            ),
                            dict(
                                name="sourceCommit",
                                value=events.EventField.from_path(
                                    "$.detail.sourceCommit"
                                ),
                            ),
                            dict(
                                name="destinationCommit",
                                value=events.EventField.from_path(
                                    "$.detail.destinationCommit"
                                ),
                            ),
                        ],
                    )
                ),
            )
        )

        # Lambda function to comment on Pull Request on Build Success/Failure
        func_update_pull_request = aws_lambda.Function(
            self,
            "UpdatePullRequest",
            code=aws_lambda.Code.from_inline(
                """import boto3

                codecommit_client = boto3.client("codecommit")


                def lambda_handler(event, context):

                    print(event)

                    for item in event["detail"]["additional-information"]["environment"][
                        "environment-variables"
                    ]:
                        if item["name"] == "pullRequestId":
                            pull_request_id = item["value"]
                        if item["name"] == "repositoryName":
                            repository_name = item["value"]
                        if item["name"] == "sourceCommit":
                            before_commit_id = item["value"]
                        if item["name"] == "destinationCommit":
                            after_commit_id = item["value"]

                    s3_prefix = (
                        "s3-{0}".format(event["region"]) if event["region"] != "us-east-1" else "s3"
                    )

                    for phase in event["detail"]["additional-information"]["phases"]:
                        if phase.get("phase-status") == "FAILED":
                            badge = "https://{0}.amazonaws.com/codefactory-{1}-prod-default-build-badges/failing.svg".format(
                                s3_prefix, event["region"]
                            )
                            content = '![Failing]({0} "Failing") - See the [Logs]({1})'.format(
                                badge, event["detail"]["additional-information"]["logs"]["deep-link"]
                            )
                            break
                        else:
                            badge = "https://{0}.amazonaws.com/codefactory-{1}-prod-default-build-badges/passing.svg".format(
                                s3_prefix, event["region"]
                            )
                            content = '![Passing]({0} "Passing") - See the [Logs]({1})'.format(
                                badge, event["detail"]["additional-information"]["logs"]["deep-link"]
                            )

                    codecommit_client.post_comment_for_pull_request(
                        pullRequestId=pull_request_id,
                        repositoryName=repository_name,
                        beforeCommitId=before_commit_id,
                        afterCommitId=after_commit_id,
                        content=content,
                    )"""
            ),
            handler="update_pull_request.lambda_handler",
            memory_size=256,
            timeout=core.Duration.seconds(30),
            # need to use 3.7 due to bug https://github.com/aws/aws-cdk/issues/6503
            runtime=aws_lambda.Runtime.PYTHON_3_7,
        )

        # Grant access to lambda to comment on Pull Request
        repo.grant(func_update_pull_request, "codecommit:PostCommentForPullRequest")

        # Codebuild event to trigger lambda function on
        codebuild_event_pattern = events.EventPattern(
            detail_type=["CodeBuild Build State Change"],
            detail={"build-status": ["SUCCEEDED", "FAILED", "STOPPED"]},
        )

        # Cloudwatch event to trigger lambda on change in codebuild state
        self.codebuild_project.on_state_change(
            "FinishBuildTrigger",
            description="Rule to trigger lambda function when Codebuild succeeds or fails",
            event_pattern=codebuild_event_pattern,
            rule_name=f"codebuild-status-trigger-lambda-{repo_name}",
            target=targets.LambdaFunction(handler=func_update_pull_request),
        )
