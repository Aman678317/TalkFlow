import { Construct } from "constructs";
import * as cdk from "aws-cdk-lib";
import * as s3deployment from "aws-cdk-lib/aws-s3-deployment";
import * as s3 from "aws-cdk-lib/aws-s3";

const configParams = require("../../config/config.params.json");

export interface FrontendS3DeploymentStackProps extends cdk.NestedStackProps {
  readonly cdkAppName: string;
  readonly webAppBucket: s3.IBucket;
}

export class FrontendS3DeploymentStack extends cdk.NestedStack {
  constructor(scope: Construct, id: string, props: FrontendS3DeploymentStackProps) {
    super(scope, id, props);

    new s3deployment.BucketDeployment(scope, `${props.cdkAppName}-WebAppDeployment`, {
      destinationBucket: props.webAppBucket,
      retainOnDelete: false,
      destinationKeyPrefix: configParams["WebAppRootPrefix"],
      sources: [
        s3deployment.Source.asset("../webapp/dist"),
        s3deployment.Source.bucket(props.webAppBucket, `${configParams["WebAppStagingPrefix"]}frontend-config.zip`),
      ],
    });
  }
}
