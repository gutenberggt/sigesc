/*
 * LUIZ-GOMES-F6.3d.2 — resolução histórica do ator no dump BSON de 18/08/2026.
 *
 * A identidade é inferida sem consulta a users: primeiro por unanimidade
 * estrutural de teacher_assignments nas quatro turmas-controle de Matemática;
 * fallback por metadados dos learning_objects. IDs técnicos nunca são emitidos.
 * O conteúdo pedagógico é reduzido a payload_present booleano.
 */
(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_F6_3C_POINT_JSON=";
  const SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa";
  const CONTROL_CLASSES = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B"];
  const TARGET_CLASSES = ["8º ANO A", "9º ANO A"];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const ACTOR_FIELDS = ["recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"];

  function sid(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }
  function norm(value) {
    return sid(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR").replace(/º/g, "o").replace(/ª/g, "a")
      .replace(/\s+/g, " ").trim();
  }
  function exists(name) { return d.getCollectionNames().includes(name); }
  function monthSummary(rows) {
    const out = {"02": 0, "03": 0, "04": 0};
    for (const row of rows) {
      const m = sid(row.date).slice(5, 7);
      if (Object.prototype.hasOwnProperty.call(out, m)) out[m] += 1;
    }
    return out;
  }
  function distinctDates(rows) {
    return [...new Set(rows.map(r => sid(r.date).slice(0, 10)).filter(Boolean))].sort();
  }
  function emit(status, classification, extra) {
    const result = Object.assign({
      schema: "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR_V1",
      status,
      overall_classification: classification,
      source_date: "2026-08-18",
      school: SCHOOL_NAME,
      period: {from: START, to_exclusive: END},
      boundaries: {
        actor_identity_derived_without_user_lookup: true,
        technical_ids_emitted: false,
        pedagogical_plaintext_emitted: false,
        pedagogical_payload_boolean_only: true,
        attendance_records_read: false,
        student_data_read: false,
        production_writes: false
      }
    }, extra || {});
    print(PREFIX + JSON.stringify(result));
  }

  const required = ["schools", "classes", "courses", "learning_objects"];
  const missing = required.filter(name => !exists(name));
  if (missing.length) {
    emit("INCONCLUSIVE", "REQUIRED_COLLECTION_MISSING", {context: {missing_count: missing.length}});
    return;
  }

  const schools = d.schools.find({name: SCHOOL_NAME}, {_id: 0, id: 1, name: 1}).toArray()
    .filter(row => norm(row.name) === norm(SCHOOL_NAME));
  if (schools.length !== 1 || !sid((schools[0] || {}).id)) {
    emit("INCONCLUSIVE", "SCHOOL_CONTEXT_NOT_UNIQUE", {context: {school_matches: schools.length}});
    return;
  }
  const schoolId = sid(schools[0].id);

  const classRows = d.classes.find({school_id: schoolId}, {_id: 0, id: 1, name: 1, academic_year: 1}).toArray();
  const classByName = {};
  const classContext = [];
  for (const name of [...CONTROL_CLASSES, ...TARGET_CLASSES]) {
    const matches = classRows.filter(row => {
      const year = sid(row.academic_year);
      return norm(row.name) === norm(name) && (year === "" || year === "2026");
    });
    classContext.push({class: name, matches: matches.length});
    if (matches.length !== 1 || !sid(matches[0].id)) {
      emit("INCONCLUSIVE", "CLASS_CONTEXT_NOT_UNIQUE", {context: {classes: classContext}});
      return;
    }
    classByName[name] = sid(matches[0].id);
  }

  const courseRows = d.courses.find({}, {_id: 0, id: 1, name: 1}).toArray();
  const mathIds = new Set(courseRows.filter(row => norm(row.name) === norm("Matemática"))
    .map(row => sid(row.id)).filter(Boolean));
  if (!mathIds.size) {
    emit("INCONCLUSIVE", "MATH_COURSE_IDENTITY_NOT_FOUND", {context: {math_identity_count: 0}});
    return;
  }
  const courseNameById = {};
  for (const row of courseRows) {
    const id = sid(row.id);
    if (id) courseNameById[id] = sid(row.name) || "<unresolved>";
  }

  const staffById = new Map();
  const staffIdsByUserId = new Map();
  if (exists("staff")) {
    for (const row of d.staff.find({}, {_id: 0, id: 1, user_id: 1}).toArray()) {
      const staffId = sid(row.id), userId = sid(row.user_id);
      if (staffId) staffById.set(staffId, row);
      if (staffId && userId) {
        if (!staffIdsByUserId.has(userId)) staffIdsByUserId.set(userId, new Set());
        staffIdsByUserId.get(userId).add(staffId);
      }
    }
  }

  const assignments = exists("teacher_assignments")
    ? d.teacher_assignments.find({}, {_id: 0, id: 1, staff_id: 1, class_id: 1, course_id: 1, academic_year: 1, status: 1}).toArray()
    : [];
  const assignmentStaffById = new Map();
  for (const row of assignments) {
    const id = sid(row.id), staffId = sid(row.staff_id);
    if (id && staffId) assignmentStaffById.set(id, staffId);
  }

  function courseId(row) { return sid(row.course_id || row.component_id); }
  function payloadProject() {
    return {$or: [
      {$ne: [{$ifNull: ["$content", ""]}, ""]},
      {$ne: [{$ifNull: ["$methodology", ""]}, ""]},
      {$ne: [{$ifNull: ["$observations", ""]}, ""]}
    ]};
  }
  function loadRows(classId, mathOnly) {
    const match = {class_id: classId, date: {$gte: START, $lt: END}};
    if (mathOnly) match.$or = [{course_id: {$in: [...mathIds]}}, {component_id: {$in: [...mathIds]}}];
    return d.learning_objects.aggregate([
      {$match: match},
      {$project: {_id: 0, date: 1, course_id: 1, component_id: 1,
        recorded_by: 1, created_by: 1, updated_by: 1, teacher_id: 1, staff_id: 1,
        assignment_id: 1, deleted: 1, status: 1, payload_present: payloadProject()}}
    ]).toArray();
  }
  function principalForRaw(value) {
    const raw = sid(value);
    if (!raw) return "";
    if (staffById.has(raw)) return `staff:${raw}`;
    const linked = staffIdsByUserId.get(raw);
    if (linked && linked.size === 1) return `staff:${[...linked][0]}`;
    return `raw:${raw}`;
  }
  function rowPrincipals(row) {
    const out = new Set();
    for (const field of ACTOR_FIELDS) {
      const p = principalForRaw(row[field]);
      if (p) out.add(p);
    }
    const aid = sid(row.assignment_id);
    if (aid) {
      const staffId = assignmentStaffById.get(aid);
      out.add(staffId ? `staff:${staffId}` : `assignment:${aid}`);
    }
    return out;
  }
  function eligibleAssignment(row, classId, allowedCourseIds) {
    const year = sid(row.academic_year), status = norm(row.status);
    return sid(row.class_id) === classId && allowedCourseIds.has(sid(row.course_id)) &&
      (year === "" || year === "2026") && !["inativo", "inactive", "cancelado", "revogado"].includes(status);
  }

  const controls = [];
  const controlRows = [];
  const assignmentStaffSets = [];
  for (const name of CONTROL_CLASSES) {
    const classId = classByName[name];
    const rows = loadRows(classId, true);
    const payloadRows = rows.filter(row => row.payload_present === true);
    if (!payloadRows.length) {
      emit("INCONCLUSIVE", "CONTROL_MATH_EVIDENCE_MISSING", {controls: [...controls, {class: name, math_rows: rows.length, math_payload_rows: 0}]});
      return;
    }
    const presentCourseIds = new Set(rows.map(courseId).filter(id => mathIds.has(id)));
    const staffSet = new Set(assignments.filter(row => eligibleAssignment(row, classId, presentCourseIds))
      .map(row => sid(row.staff_id)).filter(Boolean));
    assignmentStaffSets.push(staffSet);
    controls.push({
      class: name,
      math_rows: rows.length,
      math_payload_rows: payloadRows.length,
      months: monthSummary(payloadRows),
      dates: distinctDates(payloadRows),
      assignment_staff_candidates: staffSet.size
    });
    for (const row of rows) controlRows.push({className: name, row});
  }

  let inferredPrincipal = "";
  let inferenceSource = "";
  const nonEmptyAssignmentSets = assignmentStaffSets.filter(set => set.size > 0);
  if (nonEmptyAssignmentSets.length === CONTROL_CLASSES.length && assignmentStaffSets.every(set => set.size === 1)) {
    const values = new Set(assignmentStaffSets.map(set => [...set][0]));
    if (values.size === 1) {
      inferredPrincipal = `staff:${[...values][0]}`;
      inferenceSource = "TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS";
    }
  }

  let metadataCandidates = [];
  if (!inferredPrincipal) {
    const stats = new Map();
    for (const item of controlRows) {
      for (const principal of rowPrincipals(item.row)) {
        if (!stats.has(principal)) stats.set(principal, {rows: 0, payload_rows: 0, classes: new Set(), kind: principal.split(":", 1)[0]});
        const s = stats.get(principal);
        s.rows += 1;
        if (item.row.payload_present === true) s.payload_rows += 1;
        s.classes.add(item.className);
      }
    }
    metadataCandidates = [...stats.entries()].map(([principal, s]) => ({
      principal, rows: s.rows, payload_rows: s.payload_rows, class_support: s.classes.size,
      kind: s.kind, coverage: controlRows.length ? s.rows / controlRows.length : 0
    })).filter(item => item.class_support === CONTROL_CLASSES.length)
      .sort((a, b) => b.coverage - a.coverage || b.payload_rows - a.payload_rows || b.rows - a.rows);
    if (metadataCandidates.length) {
      const top = metadataCandidates[0], second = metadataCandidates[1];
      const tied = second && Math.abs(second.coverage - top.coverage) < 0.000001 && second.payload_rows === top.payload_rows;
      if (!tied && top.coverage >= 0.80) {
        inferredPrincipal = top.principal;
        inferenceSource = "LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT";
      }
    }
  }

  if (!inferredPrincipal) {
    emit("INCONCLUSIVE", "HISTORICAL_ACTOR_NOT_UNIQUELY_INFERRED", {
      controls,
      actor_inference: {
        status: "AMBIGUOUS_OR_INSUFFICIENT",
        assignment_unanimous: false,
        stable_metadata_candidate_count: metadataCandidates.length,
        best_metadata_coverage_percent: metadataCandidates.length ? Math.round(metadataCandidates[0].coverage * 10000) / 100 : 0
      }
    });
    return;
  }

  const inferredStaffId = inferredPrincipal.startsWith("staff:") ? inferredPrincipal.slice(6) : "";
  const topMetadata = metadataCandidates.find(item => item.principal === inferredPrincipal);

  function targetSummary(name) {
    const classId = classByName[name];
    const rows = loadRows(classId, false);
    const matching = rows.filter(row => rowPrincipals(row).has(inferredPrincipal));
    const actorPayload = matching.filter(row => row.payload_present === true);
    const actorMath = matching.filter(row => mathIds.has(courseId(row)));
    const actorMathPayload = actorMath.filter(row => row.payload_present === true);
    const actorOtherPayload = actorPayload.filter(row => !mathIds.has(courseId(row)));
    const unattributedMathPayload = rows.filter(row => row.payload_present === true && mathIds.has(courseId(row)) && rowPrincipals(row).size === 0);
    const targetAssignments = inferredStaffId ? assignments.filter(row => {
      const year = sid(row.academic_year), status = norm(row.status);
      return sid(row.staff_id) === inferredStaffId && sid(row.class_id) === classId && mathIds.has(sid(row.course_id)) &&
        (year === "" || year === "2026") && !["inativo", "inactive", "cancelado", "revogado"].includes(status);
    }) : [];
    const courseCounts = {};
    for (const row of matching) {
      const cname = courseNameById[courseId(row)] || "<unresolved>";
      courseCounts[cname] = (courseCounts[cname] || 0) + 1;
    }
    let classification = "HISTORICAL_ACTOR_ABSENT_FROM_TARGET_20260818";
    if (actorMathPayload.length) classification = "RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED";
    else if (actorOtherPayload.length) classification = "LUIZ_HISTORICAL_ROWS_UNDER_NONMATH_COMPONENT";
    else if (matching.length) classification = "LUIZ_HISTORICAL_ROWS_PRESENT_WITHOUT_PAYLOAD";
    else if (unattributedMathPayload.length) classification = "TARGET_MATH_UNATTRIBUTED_CANDIDATES_PRESENT";
    else if (targetAssignments.length) classification = "HISTORICAL_LUIZ_MATH_BINDING_PRESENT_CONTENT_ABSENT";
    return {
      class: name,
      classification,
      total_rows: rows.length,
      inferred_actor_rows: matching.length,
      inferred_actor_payload_rows: actorPayload.length,
      inferred_actor_math_rows: actorMath.length,
      inferred_actor_math_payload_rows: actorMathPayload.length,
      inferred_actor_math_payload_months: monthSummary(actorMathPayload),
      inferred_actor_math_payload_dates: distinctDates(actorMathPayload),
      inferred_actor_nonmath_payload_rows: actorOtherPayload.length,
      inferred_actor_nonmath_payload_dates: distinctDates(actorOtherPayload),
      unattributed_math_payload_rows: unattributedMathPayload.length,
      historical_math_assignment_matches: targetAssignments.length,
      inferred_actor_course_name_counts: courseCounts
    };
  }

  const targets = TARGET_CLASSES.map(targetSummary);
  const classes = targets.map(row => row.classification);
  let overall = "HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818";
  if (classes.includes("RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED")) overall = "BSON_20260818_RECOVERY_SOURCE_CONFIRMED";
  else if (classes.includes("LUIZ_HISTORICAL_ROWS_UNDER_NONMATH_COMPONENT")) overall = "BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT";
  else if (classes.includes("LUIZ_HISTORICAL_ROWS_PRESENT_WITHOUT_PAYLOAD")) overall = "BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD";
  else if (classes.includes("TARGET_MATH_UNATTRIBUTED_CANDIDATES_PRESENT")) overall = "BSON_20260818_UNATTRIBUTED_MATH_CANDIDATES";
  else if (classes.includes("HISTORICAL_LUIZ_MATH_BINDING_PRESENT_CONTENT_ABSENT")) overall = "BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT";

  emit("COMPLETED", overall, {
    actor_inference: {
      status: "EXACT_CONTROL_DERIVED",
      source: inferenceSource,
      principal_kind: inferredPrincipal.split(":", 1)[0],
      control_class_support: CONTROL_CLASSES.length,
      metadata_coverage_percent: topMetadata ? Math.round(topMetadata.coverage * 10000) / 100 : null,
      technical_identity_emitted: false
    },
    controls,
    targets
  });
})();
