import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";

import { FrontendS3DeploymentStack } from "./frontend/frontend-s3-deployment-stack";
import { FrontendConfigStack } from "./frontend/frontend-config-stack";
import { loadSSMParams } from "../config/ssm-params-util";

const configParams = require("../config/config.params.json");

export interface CdkFrontendStackProps extends cdk.StackProps {
  readonly backendStackOutputs: { key: string; value: string }[];
}

export class CdkFrontendStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CdkFrontendStackProps) {
    super(scope, id, props);

    const outputHierarchy = `${configParams.hierarchy}outputParameters`;
    new ssm.StringParameter(this, "CdkFrontendStackName", {
      parameterName: `${outputHierarchy}/CdkFrontendStackName`,
      stringValue: this.stackName,
    });

    const ssmParams = loadSSMParams(this);

    const webAppBucket = new s3.Bucket(this, "WebAppBucket", {
      bucketName: `${configParams["CdkAppName"]}-webapp-${this.account}-${this.region}`.toLowerCase(),
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const webAppCloudFrontDistribution = new cloudfront.Distribution(this, "WebAppDistribution", {
      comment: `CloudFront distribution for ${configParams["CdkAppName"]}`,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(webAppBucket, {
          originPath: `/${configParams["WebAppRootPrefix"].replace(/\/$/, "")}`,
        }),
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        compress: true,
      },
      errorResponses: [
        {
          httpStatus: 403,
          responseHttpStatus: 200,
          responsePagePath: "/index.html",
        },
      ],
    });

    new FrontendConfigStack(this, "FrontendConfigStack", {
      cdkAppName: configParams["CdkAppName"],
      webAppBucket,
      backendStackOutputs: props.backendStackOutputs,
    });

    new FrontendS3DeploymentStack(this, "FrontendS3DeploymentStack", {
      cdkAppName: configParams["CdkAppName"],
      webAppBucket,
    });

    new cdk.CfnOutput(this, "webAppBucketName", {
      value: webAppBucket.bucketName,
    });

    new cdk.CfnOutput(this, "webAppURL", {
      value: `https://${webAppCloudFrontDistribution.distributionDomainName}`,
    });
  }
}
