import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";

export interface CognitoStackProps extends cdk.NestedStackProps {
  readonly SSMParams: any;
  readonly cdkAppName: string;
}

export class CognitoStack extends cdk.NestedStack {
  public readonly authenticatedRole: iam.IRole;
  public readonly identityPool: cognito.CfnIdentityPool;
  public readonly userPool: cognito.IUserPool;
  public readonly userPoolClient: cognito.IUserPoolClient;
  public readonly userPoolDomain: cognito.CfnUserPoolDomain;
  public readonly logGroupName: string;

  constructor(scope: Construct, id: string, props: CognitoStackProps) {
    super(scope, id, props);

    const userPool = new cognito.UserPool(this, "UserPool", {
      userPoolName: `${props.cdkAppName}-UserPool`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      signInAliases: { email: true, username: false, phone: false },
      standardAttributes: { email: { required: false, mutable: true } },
    });

    const userPoolClient = new cognito.UserPoolClient(this, "UserPoolClient", {
      userPool,
      userPoolClientName: `${props.cdkAppName}-Client`,
      generateSecret: false,
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
      oAuth: {
        scopes: [cognito.OAuthScope.EMAIL, cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE],
        callbackUrls: (props.SSMParams.cognitoCallbackUrls || "https://localhost:5173").split(",").map((s: string) => s.trim()),
        logoutUrls: (props.SSMParams.cognitoLogoutUrls || "https://localhost:5173").split(",").map((s: string) => s.trim()),
      },
    });

    const userPoolDomain = new cognito.CfnUserPoolDomain(this, "UserPoolDomain", {
      domain: props.SSMParams.cognitoDomainPrefix,
      userPoolId: userPool.userPoolId,
    });

    const identityPool = new cognito.CfnIdentityPool(this, "IdentityPool", {
      identityPoolName: `${props.cdkAppName}-IdentityPool`,
      allowUnauthenticatedIdentities: false,
      cognitoIdentityProviders: [{
        clientId: userPoolClient.userPoolClientId,
        providerName: userPool.userPoolProviderName,
      }],
    });

    const authenticatedRole = new iam.Role(this, "AuthenticatedRole", {
      assumedBy: new iam.FederatedPrincipal(
        "cognito-identity.amazonaws.com",
        {
          StringEquals: { "cognito-identity.amazonaws.com:aud": identityPool.ref },
          "ForAnyValue:StringLike": { "cognito-identity.amazonaws.com:amr": "authenticated" },
        },
        "sts:AssumeRoleWithWebIdentity"
      ),
    });

    authenticatedRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "polly:SynthesizeSpeech",
          "transcribe:StartStreamTranscription",
          "transcribe:StartStreamTranscriptionWebSocket",
          "translate:TranslateText",
        ],
        resources: ["*"],
      })
    );

    const logGroup = new logs.LogGroup(this, "ConnectDesiV2VLogs", {
      logGroupName: "/aws/connect/desi-v2v-logs",
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new cognito.CfnIdentityPoolRoleAttachment(this, "RoleAttachment", {
      identityPoolId: identityPool.ref,
      roles: { authenticated: authenticatedRole.roleArn },
    });

    this.authenticatedRole = authenticatedRole;
    this.identityPool = identityPool;
    this.userPool = userPool;
    this.userPoolClient = userPoolClient;
    this.userPoolDomain = userPoolDomain;
    this.logGroupName = logGroup.logGroupName;
  }
}
