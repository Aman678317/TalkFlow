// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Custom prompt instruction for fine-tuning translation output styles.
 */
public class CustomInstruction {
    private final String role;
    private final String instruction;

    public CustomInstruction(String role, String instruction) {
        this.role = role != null ? role : "";
        this.instruction = instruction != null ? instruction : "";
    }

    public String getRole() {
        return role;
    }

    public String getInstruction() {
        return instruction;
    }

    @Override
    public String toString() {
        return (role.isEmpty() ? "" : role + ": ") + instruction;
    }
}
