(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_F6_3C_POINT_JSON=";
  const SCHOOL = "E M E I E F Jose Pereira Barbosa";
  const CONTROLS = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B"];
  const TARGETS = ["8º ANO A", "9º ANO A"];
  const ALL = [...CONTROLS, ...TARGETS];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const SKIP_KEYS = new Set([
    "content", "methodology", "observations", "resources", "records",
    "students", "student", "grades", "notes", "password", "token"
  ]);

  const sid = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "object" && typeof v.valueOf === "function") {
      try {
        const value = v.valueOf();
        if (value !== v && value !== null && value !== undefined) return String(value).trim();
      } catch (_) {}
    }
    return String(v).trim();
  };
  const norm = (v) => sid(v)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/º/g, "o")
    .replace(/ª/g, "a")
    .replace(/[._-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const exists = (name) => d.getCollectionNames().includes(name);
  const scalar = (v) => v === null || v === undefined || ["string", "number", "boolean"].includes(typeof v) || (typeof v === "object" && typeof v.valueOf === "function" && v.valueOf() !== v);
  const leaves = (obj, prefix = "", depth = 0, out = []) => {
    if (!obj || typeof obj !== "object" || depth > 4) return out;
    for (const [key, value] of Object.entries(obj)) {
      if (SKIP_KEYS.has(String(key).toLocaleLowerCase("pt-BR"))) continue;
      const path = prefix ? `${prefix}.${key}` : key;
      if (Array.isArray(value)) {
        for (const item of value.slice(0, 32)) {
          if (scalar(item)) out.push([`${path}[]`, sid(item)]);
          else leaves(item, `${path}[]`, depth + 1, out);
        }
      } else if (scalar(value)) {
        out.push([path, sid(value)]);
      } else {
        leaves(value, path, depth + 1, out);
      }
    }
    return out;
  };
  const byPath = (doc) => {
    const m = new Map();
    for (const [p, v] of leaves(doc)) {
      if (!m.has(p)) m.set(p, []);
      m.get(p).push(v);
    }
    return m;
  };
  const valuesAt = (doc, path) => byPath(doc).get(path) || [];
  const uniq = (xs) => [...new Set(xs)];
  const inPeriod = (v) => {
    const s = sid(v).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) && s >= START && s < END;
  };
  const payloadPresent = (row) => {
    const keys = ["content", "methodology", "observations", "resources"];
    return keys.some((k) => {
      const v = row && row[k];
      if (Array.isArray(v)) return v.length > 0;
      if (v && typeof v === "object") return Object.keys(v).length > 0;
      return sid(v) !== "";
    });
  };
  const targetParts = (name) => {
    const n = norm(name);
    const m = n.match(/^(6|7|8|9)(?:o)?(?: ano)? ([a-z])$/);
    return m ? { grade: m[1], section: m[2] } : null;
  };
  const gradeMatches = (value, grade) => {
    const n = norm(value);
    return n === grade || n === `${grade}o` || n === `${grade} ano` || n === `${grade}o ano` || n === `${grade}º ano`;
  };
  const sectionMatches = (value, section) => norm(value) === section;

  const boundaries = {
    source_dump_read_only: true,
    temporary_mongo_network_none: true,
    production_writes: false,
    student_data_read: false,
    attendance_records_read: false,
    grades_read: false,
    pedagogical_plaintext_emitted: false,
    technical_ids_emitted: false,
    actor_attribution_attempted: false,
    fail_closed_on_ambiguity: true,
  };
  const emit = (status, classification, extra = {}) => print(PREFIX + JSON.stringify(Object.assign({
    schema: "LUIZ_GOMES_R1_0B_SCHEMA_BRIDGE_V1",
    status,
    overall_classification: classification,
    source_date: "2026-08-18",
    period: { from: START, to_exclusive: END },
    boundaries,
  }, extra)));
  const inconclusive = (reason, diagnostics = {}) => {
    emit("INCONCLUSIVE", "HISTORICAL_SCHEMA_BRIDGE_INCONCLUSIVE", {
      insufficiency_reason: reason,
      schema_bridge: Object.assign({ terminal_state: "INCONCLUSIVE", selected: false }, diagnostics),
    });
  };

  const required = ["schools", "classes", "courses", "learning_objects"];
  const missing = required.filter((name) => !exists(name));
  if (missing.length) {
    inconclusive("REQUIRED_COLLECTION_MISSING", { missing_collection_count: missing.length });
    return;
  }

  const schoolDocs = d.schools.find({}).toArray();
  const classDocs = d.classes.find({}).toArray();
  const courseDocs = d.courses.find({}).toArray();
  const loDocs = d.learning_objects.find({}).toArray();

  // 1) Descoberta de turma por valor completo ou por composição grade+seção.
  const fullNameSolutions = [];
  const classPaths = uniq(classDocs.flatMap((doc) => leaves(doc).map(([p]) => p)));
  for (const path of classPaths) {
    const mapping = {};
    let ok = true;
    for (const name of ALL) {
      const matches = classDocs.filter((doc) => valuesAt(doc, path).some((v) => norm(v) === norm(name)));
      if (matches.length < 1) { ok = false; break; }
      mapping[name] = matches;
    }
    if (ok) fullNameSolutions.push({ mode: "FULL_VALUE", labelPaths: [path], mapping });
  }

  const compositeSolutions = [];
  for (const gradePath of classPaths) {
    for (const sectionPath of classPaths) {
      if (gradePath === sectionPath) continue;
      const mapping = {};
      let ok = true;
      for (const name of ALL) {
        const parts = targetParts(name);
        if (!parts) { ok = false; break; }
        const matches = classDocs.filter((doc) =>
          valuesAt(doc, gradePath).some((v) => gradeMatches(v, parts.grade)) &&
          valuesAt(doc, sectionPath).some((v) => sectionMatches(v, parts.section))
        );
        if (matches.length < 1) { ok = false; break; }
        mapping[name] = matches;
      }
      if (ok) compositeSolutions.push({ mode: "GRADE_SECTION_COMPOSITE", labelPaths: [gradePath, sectionPath], mapping });
    }
  }
  const namingCandidates = [...fullNameSolutions, ...compositeSolutions];
  if (!namingCandidates.length) {
    inconclusive("CLASS_LABEL_VALUE_OR_COMPOSITE_NOT_RESOLVED", {
      full_value_candidates: 0,
      composite_candidates: 0,
      class_scalar_path_count: classPaths.length,
    });
    return;
  }

  // 2) Escola por valor e relação única schools -> classes.
  const schoolNameDocs = schoolDocs.filter((doc) => leaves(doc).some(([, v]) => norm(v) === norm(SCHOOL)));
  if (schoolNameDocs.length !== 1) {
    inconclusive("SCHOOL_VALUE_NOT_UNIQUE", { school_name_matches: schoolNameDocs.length });
    return;
  }
  const schoolDoc = schoolNameDocs[0];
  const schoolLeaves = leaves(schoolDoc).filter(([, v]) => v !== "" && norm(v) !== norm(SCHOOL));
  const otherSchoolValues = new Set(
    schoolDocs.filter((doc) => doc !== schoolDoc).flatMap((doc) => leaves(doc).map(([, v]) => v)).filter(Boolean)
  );
  const uniqueSchoolIds = schoolLeaves.filter(([, v]) => !otherSchoolValues.has(v));

  const scopedNaming = [];
  for (const candidate of namingCandidates) {
    for (const [schoolIdPath, schoolIdValue] of uniqueSchoolIds) {
      for (const classSchoolPath of classPaths) {
        const resolved = {};
        let ok = true;
        for (const name of ALL) {
          const matches = candidate.mapping[name].filter((doc) => valuesAt(doc, classSchoolPath).includes(schoolIdValue));
          if (matches.length !== 1) { ok = false; break; }
          resolved[name] = matches[0];
        }
        if (ok) scopedNaming.push({ candidate, schoolIdPath, classSchoolPath, resolved });
      }
    }
  }
  if (!scopedNaming.length) {
    inconclusive("SCHOOL_CLASS_RELATION_NOT_RESOLVED", {
      naming_candidates: namingCandidates.length,
      unique_school_identity_candidates: uniqueSchoolIds.length,
    });
    return;
  }

  // 3) Ponte classes -> learning_objects por valores referenciais, exigindo evidência nos 4 controles.
  const loPaths = uniq(loDocs.flatMap((doc) => leaves(doc).map(([p]) => p)));
  const classBridgeCandidates = [];
  for (const scoped of scopedNaming) {
    for (const classIdPath of classPaths) {
      const ids = {};
      let distinct = true;
      for (const name of ALL) {
        const vals = uniq(valuesAt(scoped.resolved[name], classIdPath).filter(Boolean));
        if (vals.length !== 1) { distinct = false; break; }
        ids[name] = vals[0];
      }
      if (!distinct || new Set(Object.values(ids)).size !== ALL.length) continue;
      for (const loClassPath of loPaths) {
        const controlHits = CONTROLS.map((name) => loDocs.filter((row) => valuesAt(row, loClassPath).includes(ids[name])).length);
        if (!controlHits.every((n) => n > 0)) continue;
        classBridgeCandidates.push({ scoped, classIdPath, loClassPath, ids, controlHits });
      }
    }
  }
  if (!classBridgeCandidates.length) {
    inconclusive("CLASS_REFERENCE_RELATION_NOT_RESOLVED", {
      scoped_naming_candidates: scopedNaming.length,
      learning_object_scalar_path_count: loPaths.length,
    });
    return;
  }

  // 4) Matemática por valor e relação courses -> learning_objects.
  const coursePaths = uniq(courseDocs.flatMap((doc) => leaves(doc).map(([p]) => p)));
  const mathDocsByNamePath = [];
  for (const path of coursePaths) {
    const matches = courseDocs.filter((doc) => valuesAt(doc, path).some((v) => norm(v) === norm("Matemática")));
    if (matches.length) mathDocsByNamePath.push({ courseNamePath: path, docs: matches });
  }
  if (!mathDocsByNamePath.length) {
    inconclusive("MATH_COURSE_VALUE_NOT_RESOLVED", { course_scalar_path_count: coursePaths.length });
    return;
  }

  const mathBridgeCandidates = [];
  for (const nameCandidate of mathDocsByNamePath) {
    for (const courseIdPath of coursePaths) {
      const mathIds = uniq(nameCandidate.docs.flatMap((doc) => valuesAt(doc, courseIdPath)).filter(Boolean));
      if (!mathIds.length) continue;
      const mathSet = new Set(mathIds);
      for (const loCoursePath of loPaths) {
        const overlap = loDocs.some((row) => valuesAt(row, loCoursePath).some((v) => mathSet.has(v)));
        if (overlap) mathBridgeCandidates.push({ courseNamePath: nameCandidate.courseNamePath, courseIdPath, loCoursePath, mathIds, mathSet });
      }
    }
  }
  if (!mathBridgeCandidates.length) {
    inconclusive("MATH_REFERENCE_RELATION_NOT_RESOLVED", { math_name_candidates: mathDocsByNamePath.length });
    return;
  }

  // 5) Data: valor temporal válido no período e quatro controles com Matemática.
  const datePaths = loPaths.filter((path) => loDocs.some((row) => valuesAt(row, path).some(inPeriod)));
  if (!datePaths.length) {
    inconclusive("LEARNING_OBJECT_DATE_VALUE_NOT_RESOLVED", {});
    return;
  }

  const solutions = [];
  for (const cls of classBridgeCandidates) {
    for (const math of mathBridgeCandidates) {
      for (const datePath of datePaths) {
        const rowCounts = {};
        let controlsOk = true;
        for (const name of ALL) {
          const rows = loDocs.filter((row) =>
            valuesAt(row, cls.loClassPath).includes(cls.ids[name]) &&
            valuesAt(row, math.loCoursePath).some((v) => math.mathSet.has(v)) &&
            valuesAt(row, datePath).some(inPeriod)
          );
          rowCounts[name] = rows.length;
          if (CONTROLS.includes(name) && rows.length === 0) controlsOk = false;
        }
        if (!controlsOk) continue;
        solutions.push({ cls, math, datePath, rowCounts });
      }
    }
  }

  // Dedupe por resultado estrutural, não por aliases equivalentes que carreguem os mesmos valores.
  const dedup = new Map();
  for (const s of solutions) {
    const signature = [
      ALL.map((name) => s.cls.ids[name]).join("|"),
      s.cls.loClassPath,
      [...s.math.mathSet].sort().join("|"),
      s.math.loCoursePath,
      s.datePath,
      s.cls.scoped.classSchoolPath,
    ].join("::");
    if (!dedup.has(signature)) dedup.set(signature, s);
  }
  const uniqueSolutions = [...dedup.values()];
  if (uniqueSolutions.length !== 1) {
    inconclusive(uniqueSolutions.length === 0 ? "NO_STRUCTURAL_BRIDGE_SOLUTION" : "MULTIPLE_STRUCTURAL_BRIDGE_SOLUTIONS", {
      raw_solution_count: solutions.length,
      deduplicated_solution_count: uniqueSolutions.length,
      class_bridge_candidates: classBridgeCandidates.length,
      math_bridge_candidates: mathBridgeCandidates.length,
      date_candidates: datePaths.length,
    });
    return;
  }

  const selected = uniqueSolutions[0];
  const summaries = [];
  for (const name of ALL) {
    const rows = loDocs.filter((row) =>
      valuesAt(row, selected.cls.loClassPath).includes(selected.cls.ids[name]) &&
      valuesAt(row, selected.math.loCoursePath).some((v) => selected.math.mathSet.has(v)) &&
      valuesAt(row, selected.datePath).some(inPeriod)
    );
    summaries.push({
      class_name: name,
      role: CONTROLS.includes(name) ? "CONTROL" : "TARGET",
      math_rows_in_period: rows.length,
      rows_with_payload: rows.filter(payloadPresent).length,
      distinct_dates: uniq(rows.flatMap((row) => valuesAt(row, selected.datePath).filter(inPeriod).map((v) => sid(v).slice(0, 10)))).length,
    });
  }
  const targetRows = summaries.filter((x) => x.role === "TARGET").reduce((a, x) => a + x.math_rows_in_period, 0);
  const targetPayload = summaries.filter((x) => x.role === "TARGET").reduce((a, x) => a + x.rows_with_payload, 0);
  const classification = targetRows === 0
    ? "SCHEMA_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS"
    : (targetPayload > 0 ? "SCHEMA_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT" : "SCHEMA_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD");

  emit("COMPLETED", classification, {
    schema_bridge: {
      terminal_state: "RESOLVED",
      selected: true,
      resolution_mode: selected.cls.scoped.candidate.mode,
      class_label_paths: selected.cls.scoped.candidate.labelPaths,
      school_relation: { school_identity_path: selected.cls.scoped.schoolIdPath, class_school_ref_path: selected.cls.scoped.classSchoolPath },
      class_relation: { class_identity_path: selected.cls.classIdPath, learning_object_class_ref_path: selected.cls.loClassPath },
      math_relation: { course_name_path: selected.math.courseNamePath, course_identity_path: selected.math.courseIdPath, learning_object_course_ref_path: selected.math.loCoursePath },
      learning_object_date_path: selected.datePath,
      control_requirement: "FOUR_CONTROLS_WITH_MATH_IN_PERIOD",
      deduplicated_solution_count: 1,
    },
    classes: summaries,
    targets_total_math_rows: targetRows,
    targets_total_rows_with_payload: targetPayload,
    next_gate_r1_0c_open: targetRows > 0,
  });
})();
