// Cognito authentication and AWS credential management for Amazon Connect
import { COGNITO_CONFIG } from "../config";
import { LOGGER_PREFIX } from "../constants";

let _credentials = null;

export function hasValidAwsCredentials() {
  if (!_credentials) return false;
  return _credentials.expiration > new Date(Date.now() + 60000);
}

export async function getValidAwsCredentials() {
  if (hasValidAwsCredentials()) {
    return _credentials;
  }

  // Attempt to load from session storage or refresh token
  const idToken = sessionStorage.getItem("cognito_id_token");
  if (!idToken) {
    console.warn(`${LOGGER_PREFIX} - No active Cognito session. Operating in local mode.`);
    return {
      accessKeyId: "local_dev_key",
      secretAccessKey: "local_dev_secret",
      sessionToken: "local_dev_token",
      expiration: new Date(Date.now() + 3600000)
    };
  }

  try {
    const loginsKey = `cognito-idp.${COGNITO_CONFIG.region}.amazonaws.com/${COGNITO_CONFIG.userPoolId}`;
    const identityPoolId = COGNITO_CONFIG.identityPoolId;

    // Exchange token via Cognito Identity
    const getIdResponse = await fetch(`https://cognito-identity.${COGNITO_CONFIG.region}.amazonaws.com/`, {
      method: "POST",
      headers: {
        "X-Amz-Target": "AWSCognitoIdentityService.GetId",
        "Content-Type": "application/x-amz-json-1.1"
      },
      body: JSON.stringify({
        IdentityPoolId: identityPoolId,
        Logins: { [loginsKey]: idToken }
      })
    });

    const idData = await getIdResponse.json();
    const getCredsResponse = await fetch(`https://cognito-identity.${COGNITO_CONFIG.region}.amazonaws.com/`, {
      method: "POST",
      headers: {
        "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
        "Content-Type": "application/x-amz-json-1.1"
      },
      body: JSON.stringify({
        IdentityId: idData.IdentityId,
        Logins: { [loginsKey]: idToken }
      })
    });

    const credsData = await getCredsResponse.json();
    _credentials = {
      accessKeyId: credsData.Credentials.AccessKeyId,
      secretAccessKey: credsData.Credentials.SecretKey,
      sessionToken: credsData.Credentials.SessionToken,
      expiration: new Date(credsData.Credentials.Expiration * 1000)
    };
    return _credentials;
  } catch (error) {
    console.error(`${LOGGER_PREFIX} - Error fetching Cognito credentials:`, error);
    return {
      accessKeyId: "local_dev_key",
      secretAccessKey: "local_dev_secret",
      sessionToken: "local_dev_token",
      expiration: new Date(Date.now() + 3600000)
    };
  }
}

export function handleAuthRedirect() {
  const hash = window.location.hash.substring(1);
  const params = new URLSearchParams(hash);
  const idToken = params.get("id_token");
  if (idToken) {
    sessionStorage.setItem("cognito_id_token", idToken);
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}
