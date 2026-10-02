// Runtime configuration loader for Amazon Connect Desi V2V
export const COGNITO_CONFIG = {
  region: getParamValue(window.WebappConfig?.backendRegion),
  cognitoDomain: getParamValue(window.WebappConfig?.cognitoDomainURL),
  identityPoolId: getParamValue(window.WebappConfig?.identityPoolId),
  userPoolId: getParamValue(window.WebappConfig?.userPoolId),
  clientId: getParamValue(window.WebappConfig?.userPoolWebClientId),
};

export const CONNECT_CONFIG = {
  connectInstanceURL: getParamValue(window.WebappConfig?.connectInstanceURL),
  connectInstanceRegion: getParamValue(window.WebappConfig?.connectInstanceRegion),
};

export const TRANSCRIBE_CONFIG = {
  transcribeRegion: getParamValue(window.WebappConfig?.transcribeRegion),
};

export const TRANSLATE_CONFIG = {
  translateRegion: getParamValue(window.WebappConfig?.translateRegion),
  translateProxyEnabled: getBoolParamValue(window.WebappConfig?.translateProxyEnabled),
  translateProxyHostname: window.location?.hostname,
};

export const POLLY_CONFIG = {
  pollyRegion: getParamValue(window.WebappConfig?.pollyRegion),
  pollyProxyEnabled: getBoolParamValue(window.WebappConfig?.pollyProxyEnabled),
  pollyProxyHostname: window.location?.hostname,
};

function getParamValue(param) {
  const SSM_NOT_DEFINED = "not-defined";
  if (!param || param === SSM_NOT_DEFINED) return undefined;
  return param;
}

function getBoolParamValue(param) {
  return param === "true" || param === true;
}
