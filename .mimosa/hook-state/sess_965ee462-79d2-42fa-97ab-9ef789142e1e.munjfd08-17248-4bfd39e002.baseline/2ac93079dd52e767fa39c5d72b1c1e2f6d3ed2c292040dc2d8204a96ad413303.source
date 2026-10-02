#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { CdkBackendStack } from "../lib/cdk-backend-stack";
import { CdkFrontendStack } from "../lib/cdk-frontend-stack";
const configParams = require("../config/config.params.json");

const app = new cdk.App();

const backendStack = new CdkBackendStack(app, configParams["CdkBackendStack"], {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});

new CdkFrontendStack(app, configParams["CdkFrontendStack"], {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
  backendStackOutputs: backendStack.backendStackOutputs,
});
