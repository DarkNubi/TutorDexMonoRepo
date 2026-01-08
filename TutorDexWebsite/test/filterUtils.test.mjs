import { expect } from "chai";
import { matchesFilters, canonicalizePair } from "../src/lib/filterUtils.js";

describe("filterUtils", () => {
  describe("matchesFilters", () => {
    it("returns true when job satisfies filters", () => {
      const job = {
        signalsLevels: ["Secondary"],
        signalsSpecificLevels: ["Sec 3"],
        subjectsGeneral: ["MATH"],
        subjectsCanonical: ["JC.H2.MATH"],
        location: "Central",
        rateMin: 40,
      };
      const filters = {
        level: "Secondary",
        specificStudentLevel: "Sec 3",
        subjectGeneral: "MATH",
        subjectCanonical: "JC.H2.MATH",
        location: "Central",
        minRate: "30",
      };
      expect(matchesFilters(job, filters)).to.be.true;
    });

    it("returns false when minRate is higher than job rate", () => {
      const job = { rateMin: 25 };
      const filters = { minRate: "30" };
      expect(matchesFilters(job, filters)).to.be.false;
    });

    it("returns false when location does not match", () => {
      const job = { location: "East" };
      const filters = { location: "West" };
      expect(matchesFilters(job, filters)).to.be.false;
    });
  });

  describe("canonicalizePair", () => {
    it("returns original when looks like canonical code", () => {
      const code = "ABC.DEF";
      expect(canonicalizePair("Secondary", code)).to.equal(code);
    });

    it("does not throw for unknown labels and returns a string", () => {
      const out = canonicalizePair("Secondary", "NonExistent Subject Label");
      expect(out).to.be.a("string");
    });
  });
});
