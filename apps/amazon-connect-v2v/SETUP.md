# Amazon Connect with Desi Voice-to-Voice (V2V) Setup Guide

This guide details the step-by-step procedure to deploy the Desi Voice-to-Voice translation solution with Amazon Connect.

---

## 📋 Prerequisites

1. **AWS Account & IAM Permissions**: Administrator access for CDK deployments.
2. **Amazon Connect Instance**: An active Amazon Connect instance in your target region (e.g. `us-east-1` or `eu-west-2`).
3. **Desi API Key**: A valid `DESI_API_KEY` (or `GTK_API_KEY`) from [GlobalTalk AI / Desi Developers](https://globaltalk.ai/developers).
4. **Local Tools**:
   - Node.js 20.x or higher & npm
   - AWS CLI v2 configured with active credentials
   - AWS CDK v2 (`npm i -g aws-cdk`)

---

## 🛠️ Deployment Steps

### Step 1: Install Dependencies

From the `apps/amazon-connect-v2v` directory:

```bash
cd cdk-stacks
npm run install:all
```

---

### Step 2: Configure Deployment Parameters

Run the interactive CDK configuration wizard:

```bash
npm run configure
```

Provide the following values when prompted:
- **`cognito-domain-prefix`**: A unique prefix for the Cognito hosted UI (e.g., `connect-desi-v2v-<org>`).
- **`cognito-callback-urls`**: Initially set to `https://localhost:5173` (add CloudFront URL after deployment).
- **`cognito-logout-urls`**: Initially set to `https://localhost:5173`.
- **`connect-instance-url`**: Your Connect instance URL (e.g., `https://<alias>.my.connect.aws`).
- **`connect-instance-region`**: Region of your Connect instance (e.g. `us-east-1`).
- **`transcribe-region`**, **`translate-region`**, **`polly-region`**: Fallback AWS speech regions (e.g. `us-east-1`).

---

### Step 3: Deploy CDK Stacks

Deploy the backend Cognito pool and frontend CloudFront/S3 distributions:

```bash
npm run build:deploy:all
```

Once deployment completes, note down the output values:
- `userPoolId`
- `webAppURL` (your CloudFront distribution URL, e.g. `https://d123456abcdef8.cloudfront.net`)

---

### Step 4: Deploy the Desi Proxy Lambda Functions

The web application securely accesses the Desi Voice-to-Voice real-time API via two Lambda Function URLs:
- `desi-v2v-request-session`: Creates real-time streaming sessions.
- `desi-v2v-get-languages`: Discovers supported languages and formality matrix.

Navigate to the `lambda-functions` directory:

```bash
cd ../lambda-functions
export REGION="us-east-1"
```

1. **Package the Lambda functions**:
   ```bash
   (cd request-session && zip -qr ../request-session-deploy.zip index.mjs)
   (cd get-languages && zip -qr ../get-languages-deploy.zip index.mjs)
   ```

2. **Create IAM Execution Role**:
   ```bash
   aws iam create-role \
     --role-name desi-v2v-lambda-role \
     --assume-role-policy-document file://trust-policy.json

   aws iam attach-role-policy \
     --role-name desi-v2v-lambda-role \
     --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

   ROLE_ARN=$(aws iam get-role --role-name desi-v2v-lambda-role --query 'Role.Arn' --output text)
   ```

3. **Deploy Lambda Functions**:
   ```bash
   aws lambda create-function \
     --function-name desi-v2v-request-session \
     --runtime nodejs20.x \
     --handler index.handler \
     --role "$ROLE_ARN" \
     --zip-file fileb://request-session-deploy.zip \
     --timeout 30 \
     --region "$REGION"

   aws lambda create-function \
     --function-name desi-v2v-get-languages \
     --runtime nodejs20.x \
     --handler index.handler \
     --role "$ROLE_ARN" \
     --zip-file fileb://get-languages-deploy.zip \
     --timeout 30 \
     --region "$REGION"
   ```

4. **Set Desi API Key & Base URL**:
   ```bash
   aws lambda update-function-configuration \
     --function-name desi-v2v-request-session \
     --environment "Variables={DESI_API_KEY=your-desi-api-key,DESI_DEV_API_KEY=your-desi-dev-key,DESI_API_URL=https://api.globaltalk.ai}" \
     --region "$REGION"

   aws lambda update-function-configuration \
     --function-name desi-v2v-get-languages \
     --environment "Variables={DESI_API_KEY=your-desi-api-key,DESI_API_URL=https://api.globaltalk.ai}" \
     --region "$REGION"
   ```

5. **Enable Public Function URLs with CORS**:
   ```bash
   for FN in desi-v2v-request-session desi-v2v-get-languages; do
     aws lambda create-function-url-config \
       --function-name "$FN" \
       --auth-type NONE \
       --cors file://cors-config.json \
       --region "$REGION"

     aws lambda add-permission \
       --function-name "$FN" \
       --statement-id FunctionURLAllowPublicAccess \
       --action lambda:InvokeFunctionUrl \
       --principal "*" \
       --function-url-auth-type NONE \
       --region "$REGION"
   done
   ```

6. **Retrieve Function URLs**:
   ```bash
   aws lambda get-function-url-config --function-name desi-v2v-request-session --query 'FunctionUrl' --output text --region "$REGION"
   aws lambda get-function-url-config --function-name desi-v2v-get-languages --query 'FunctionUrl' --output text --region "$REGION"
   ```

---

### Step 5: Wire Lambda URLs into Webapp & Redeploy

In `webapp/.env`:

```bash
VITE_GET_LANGUAGES_PROXY=https://<your-get-languages-id>.lambda-url.<region>.on.aws/
VITE_REQUEST_SESSION_PROXY=https://<your-request-session-id>.lambda-url.<region>.on.aws/
```

Rebuild and redeploy:

```bash
cd ../cdk-stacks
npm run build:deploy:all
```

---

### Step 6: Configure Amazon Connect Approved Origins

1. In the AWS Console, open **Amazon Connect**.
2. Select your instance alias $\to$ **Approved origins**.
3. Click **Add Domain** and add:
   - Your CloudFront URL (e.g., `https://d123456abcdef8.cloudfront.net`)
   - For local development: `https://localhost:5173`

---

### Step 7: Local Development Testing

To run the webapp locally:

1. `npm run sync-config` (downloads `frontend-config.js` to `webapp/`).
2. Navigate to `webapp/` and run:
   ```bash
   npm run dev
   ```
3. Open `https://localhost:5173`. Accept the self-signed SSL certificate (via mkcert).
4. Log in using your Cognito credentials, authorize the microphone, and test full bidirectional voice translation!
