// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api.model;

/**
 * Character and document translation usage and limits for the authenticated account.
 */
public class Usage {
    public static class Detail {
        private final long count;
        private final long limit;

        public Detail(long count, long limit) {
            this.count = count;
            this.limit = limit;
        }

        public long getCount() {
            return count;
        }

        public long getLimit() {
            return limit;
        }

        @Override
        public String toString() {
            return count + " / " + limit;
        }
    }

    private final Detail character;
    private final Detail document;
    private final Detail teamDocument;
    private final double speechToTextMinutes;
    private final double speechToSpeechMinutes;

    public Usage(
            long charCount, long charLimit,
            long docCount, long docLimit,
            long teamDocCount, long teamDocLimit,
            double speechToTextMinutes,
            double speechToSpeechMinutes) {
        this.character = new Detail(charCount, charLimit);
        this.document = new Detail(docCount, docLimit);
        this.teamDocument = new Detail(teamDocCount, teamDocLimit);
        this.speechToTextMinutes = speechToTextMinutes;
        this.speechToSpeechMinutes = speechToSpeechMinutes;
    }

    public Detail getCharacter() {
        return character;
    }

    public Detail getDocument() {
        return document;
    }

    public Detail getTeamDocument() {
        return teamDocument;
    }

    public double getSpeechToTextMinutes() {
        return speechToTextMinutes;
    }

    public double getSpeechToSpeechMinutes() {
        return speechToSpeechMinutes;
    }

    public boolean isCharacterLimitExceeded() {
        return character.getLimit() > 0 && character.getCount() >= character.getLimit();
    }

    @Override
    public String toString() {
        return "Usage{Characters: " + character + ", Documents: " + document + "}";
    }
}
