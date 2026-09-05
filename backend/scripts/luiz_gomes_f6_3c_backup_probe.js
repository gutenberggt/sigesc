/*
 * LUIZ-GOMES-F6.3c — probe executado SOMENTE em Mongo restaurado e isolado.
 *
 * Não lê texto pedagógico, attendance.records, estudantes, matrículas ou notas.
 * Não emite IDs técnicos. O objetivo é localizar, em backups históricos retidos,
 * metadados de conteúdo atribuíveis ao Luiz nas turmas 8º/9º ANO A em fev-abr/2026.
 */
(() => {
  const d = db.getSiblingDB("sigesc");
  const TEACHER_NAME = "Luiz Gomes dos Santos";
  const SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa";
  const TARGET_CLASSES = ["8º ANO A", "9º ANO A"];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const ACTOR_FIELDS = ["recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"];

  function sid(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function norm(value) {
    return sid(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .replace(/º/g, "o")
      .replace(/ª/g, "a")
      .replace(/\s+/g, " ")
      .trim();
  }

  function collectionExists(name) {
    return d.getCollectionNames().includes(name);
  }

  function monthSummary(rows) {
    const out = {"02": 0, "03": 0, "04": 0};
    for (const row of rows) {
      const day = sid(row.date).slice(0, 10);
      const month = day.slice(5, 7);
      if (Object.prototype.hasOwnProperty.call(out, month)) out[month] += 1;
    }
    return out;
  }

  function distinctDates(rows) {
    return [...new Set(rows.map(r => sid(r.date).slice(0, 10)).filter(Boolean))].sort();
  }

  function exactByName(collection, fields, expected) {
    if (!collectionExists(collection)) return [];
    const projection = {_id: 0};
    for (const field of fields) projection[field] = 1;
    return d.getCollection(collection).find({}, projection).toArray().filter(row => {
      return fields.some(field => norm(row[field]) === norm(expected));
    });
  }

  const users = exactByName("users", ["full_name", "name"], TEACHER_NAME);
  if (users.length !== 1) throw new Error(`F63C_TEACHER_USER_MATCHES:${users.length}`);
  const user = users[0];
  const userId = sid(user.id);
  if (!userId) throw new Error("F63C_TEACHER_USER_ID_MISSING");

  const staffRows = collectionExists("staff")
    ? d.staff.find({user_id: userId}, {_id: 0, id: 1, user_id: 1, school_id: 1, mantenedora_id: 1}).toArray()
    : [];
  const actorIds = new Set([userId, ...staffRows.map(row => sid(row.id)).filter(Boolean)]);

  const schools = exactByName("schools", ["name"], SCHOOL_NAME);
  if (schools.length !== 1) throw new Error(`F63C_SCHOOL_MATCHES:${schools.length}`);
  const schoolId = sid(schools[0].id);
  if (!schoolId) throw new Error("F63C_SCHOOL_ID_MISSING");

  const classes = collectionExists("classes")
    ? d.classes.find(
        {school_id: schoolId},
        {_id: 0, id: 1, name: 1, academic_year: 1, school_id: 1}
      ).toArray()
    : [];
  const classByName = {};
  for (const target of TARGET_CLASSES) {
    const matches = classes.filter(row => {
      const year = sid(row.academic_year);
      return norm(row.name) === norm(target) && (year === "" || year === "2026");
    });
    if (matches.length !== 1) throw new Error(`F63C_CLASS_MATCHES:${target}:${matches.length}`);
    classByName[target] = sid(matches[0].id);
  }

  const courseById = {};
  if (collectionExists("courses")) {
    for (const row of d.courses.find({}, {_id: 0, id: 1, name: 1}).toArray()) {
      if (sid(row.id)) courseById[sid(row.id)] = sid(row.name) || "<unresolved>";
    }
  }

  const assignmentIds = new Set();
  if (collectionExists("teacher_assignments")) {
    for (const row of d.teacher_assignments.find(
      {staff_id: {$in: [...actorIds]}},
      {_id: 0, id: 1}
    ).toArray()) {
      if (sid(row.id)) assignmentIds.add(sid(row.id));
    }
  }
  if (collectionExists("teacher_class_assignments")) {
    for (const row of d.teacher_class_assignments.find(
      {teacher_id: userId},
      {_id: 0, id: 1}
    ).toArray()) {
      if (sid(row.id)) assignmentIds.add(sid(row.id));
    }
  }

  function courseId(row) {
    return sid(row.course_id || row.component_id);
  }

  function actorCategory(row) {
    const values = new Set(ACTOR_FIELDS.map(field => sid(row[field])).filter(Boolean));
    for (const value of values) {
      if (actorIds.has(value)) return "LUIZ";
    }
    const assignmentId = sid(row.assignment_id);
    if (assignmentId && assignmentIds.has(assignmentId)) return "LUIZ";
    if (values.size > 0) return "FOREIGN_ACTOR_PRESENT";
    return "NO_ACTOR_METADATA";
  }

  function storeRows(store, classId) {
    if (!collectionExists(store)) return [];
    return d.getCollection(store).find(
      {class_id: classId, date: {$gte: START, $lt: END}},
      {
        _id: 0,
        date: 1,
        course_id: 1,
        component_id: 1,
        recorded_by: 1,
        created_by: 1,
        updated_by: 1,
        teacher_id: 1,
        staff_id: 1,
        assignment_id: 1,
      }
    ).toArray();
  }

  function storeSummary(store, rows) {
    const enriched = rows.map(row => {
      const cid = courseId(row);
      const cname = courseById[cid] || "<unresolved>";
      return {
        date: sid(row.date).slice(0, 10),
        actor: actorCategory(row),
        course_name: cname,
        math_named: norm(cname) === norm("Matemática"),
      };
    });
    const luiz = enriched.filter(row => row.actor === "LUIZ");
    const math = enriched.filter(row => row.math_named);
    const luizMath = enriched.filter(row => row.actor === "LUIZ" && row.math_named);
    const luizOther = enriched.filter(row => row.actor === "LUIZ" && !row.math_named);
    const noActorMath = enriched.filter(row => row.actor === "NO_ACTOR_METADATA" && row.math_named);
    const foreignMath = enriched.filter(row => row.actor === "FOREIGN_ACTOR_PRESENT" && row.math_named);
    const courseCounts = {};
    for (const row of enriched) {
      const key = row.course_name || "<unresolved>";
      courseCounts[key] = (courseCounts[key] || 0) + 1;
    }
    return {
      store,
      documents: enriched.length,
      actor_partition: {
        LUIZ: luiz.length,
        FOREIGN_ACTOR_PRESENT: enriched.filter(row => row.actor === "FOREIGN_ACTOR_PRESENT").length,
        NO_ACTOR_METADATA: enriched.filter(row => row.actor === "NO_ACTOR_METADATA").length,
      },
      math_named_rows: math.length,
      luiz_attributed_rows: luiz.length,
      luiz_math_rows: luizMath.length,
      luiz_math_months: monthSummary(luizMath),
      luiz_math_dates: distinctDates(luizMath),
      luiz_other_component_rows: luizOther.length,
      luiz_other_component_dates: distinctDates(luizOther),
      no_actor_math_rows: noActorMath.length,
      no_actor_math_dates: distinctDates(noActorMath),
      foreign_math_rows: foreignMath.length,
      course_name_counts: courseCounts,
    };
  }

  function auditSummary(classId) {
    if (!collectionExists("audit_logs")) return {events: 0, months: {"02": 0, "03": 0, "04": 0}, dates: []};
    const rows = d.audit_logs.find(
      {
        user_id: userId,
        collection: {$in: ["learning_objects", "content_entries"]},
        "extra_data.class_id": classId,
        "extra_data.date": {$gte: START, $lt: END},
      },
      {_id: 0, action: 1, collection: 1, "extra_data.date": 1, "extra_data.class_id": 1}
    ).toArray().map(row => ({date: sid((row.extra_data || {}).date).slice(0, 10)}));
    return {events: rows.length, months: monthSummary(rows), dates: distinctDates(rows)};
  }

  const targets = [];
  for (const className of TARGET_CLASSES) {
    const classId = classByName[className];
    const stores = [
      storeSummary("learning_objects", storeRows("learning_objects", classId)),
      storeSummary("content_entries", storeRows("content_entries", classId)),
    ];
    const luizMathTotal = stores.reduce((sum, item) => sum + item.luiz_math_rows, 0);
    const luizTargetTotal = stores.reduce((sum, item) => sum + item.luiz_attributed_rows, 0);
    const noActorMathTotal = stores.reduce((sum, item) => sum + item.no_actor_math_rows, 0);
    let classification = "NO_LUIZ_MATH_ROWS_IN_BACKUP";
    if (luizMathTotal > 0) classification = "RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED";
    else if (luizTargetTotal > 0) classification = "LUIZ_TARGET_ROWS_PRESENT_UNDER_NONMATH_COMPONENT";
    else if (noActorMathTotal > 0) classification = "UNATTRIBUTED_MATH_CANDIDATES_PRESENT";
    targets.push({
      class: className,
      classification,
      stores,
      audit_logs: auditSummary(classId),
    });
  }

  const result = {
    schema: "LUIZ_GOMES_F6_3C_BACKUP_POINT_METADATA_V1",
    teacher: TEACHER_NAME,
    school: SCHOOL_NAME,
    period: {from: START, to_exclusive: END},
    targets,
    boundaries: {
      pedagogical_plaintext_read: false,
      attendance_records_read: false,
      student_data_read: false,
      technical_ids_emitted: false,
      restored_collections_limited: true,
    },
  };
  print("LUIZ_GOMES_F6_3C_POINT_JSON=" + JSON.stringify(result));
})();
