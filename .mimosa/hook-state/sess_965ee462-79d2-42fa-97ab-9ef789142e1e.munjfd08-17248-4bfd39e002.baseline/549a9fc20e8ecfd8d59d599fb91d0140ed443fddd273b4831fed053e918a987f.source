// --------------------------------------------------------------------------------------------------
// <copyright file="JsonUtils.cs" company="GlobalTalk AI Authors">
//   Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
//   Licensed under the MIT License.
// </copyright>
// --------------------------------------------------------------------------------------------------

using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Desi.Internal {
  /// <summary>
  /// Internal JSON serialization utilities for the Desi .NET Client.
  /// </summary>
  internal static class JsonUtils {
    public static readonly JsonSerializerOptions DefaultOptions = new JsonSerializerOptions {
      PropertyNameCaseInsensitive = true,
      PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
      DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
      WriteIndented = false
    };

    public static string Serialize<T>(T value) {
      return JsonSerializer.Serialize(value, DefaultOptions);
    }

    public static T? Deserialize<T>(string json) {
      return JsonSerializer.Deserialize<T>(json, DefaultOptions);
    }

    public static ValueTask<T?> DeserializeAsync<T>(Stream stream, CancellationToken cancellationToken = default) {
      return JsonSerializer.DeserializeAsync<T>(stream, DefaultOptions, cancellationToken);
    }
  }
}
