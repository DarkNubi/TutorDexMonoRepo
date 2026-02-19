import { expect } from "chai";
import { sanitizeNext, sanitizeNotice } from "../auth.js";

describe("auth sanitizers", () => {
  describe("sanitizeNext", () => {
    it("allows only allowlisted destinations", () => {
      expect(sanitizeNext("assignments.html")).to.equal("assignments.html");
      expect(sanitizeNext("profile.html")).to.equal("profile.html");
      expect(sanitizeNext("index.html")).to.equal("index.html");
    });

    it("rejects empty and non-allowlisted values", () => {
      expect(sanitizeNext("")).to.equal(null);
      expect(sanitizeNext("auth.html")).to.equal(null);
      expect(sanitizeNext("reset-password.html")).to.equal(null);
      expect(sanitizeNext("profile.html?x=1")).to.equal(null);
    });

    it("rejects open redirect attempts and path traversal", () => {
      expect(sanitizeNext("https://evil.example")).to.equal(null);
      expect(sanitizeNext("//evil.example")).to.equal(null);
      expect(sanitizeNext("../profile.html")).to.equal(null);
      expect(sanitizeNext("foo/profile.html")).to.equal(null);
      expect(sanitizeNext("profile.html\\evil")).to.equal(null);
      expect(sanitizeNext("javascript:alert(1)")).to.equal(null);
    });

    it("rejects whitespace in the value", () => {
      expect(sanitizeNext("profile.html\tfoo")).to.equal(null);
      expect(sanitizeNext("profile.html foo")).to.equal(null);
    });
  });

  describe("sanitizeNotice", () => {
    it("allows only allowlisted notice keys", () => {
      expect(sanitizeNotice("password_reset_success")).to.equal("password_reset_success");
      expect(sanitizeNotice("signed_out")).to.equal("signed_out");
      expect(sanitizeNotice("session_expired")).to.equal("session_expired");
      expect(sanitizeNotice("password_reset_email_sent")).to.equal("password_reset_email_sent");
      expect(sanitizeNotice("password_reset_link_invalid")).to.equal("password_reset_link_invalid");
    });

    it("rejects empty and unknown keys", () => {
      expect(sanitizeNotice("")).to.equal(null);
      expect(sanitizeNotice("not_a_real_notice")).to.equal(null);
      expect(sanitizeNotice("signed-out")).to.equal(null);
    });
  });
});

