export const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

export const EMPTY_HEALTH_PROFILE = {
  blood_type: null,
  has_allergies: null,
  allergies_description: null,
  has_comorbidities: null,
  comorbidities_description: null,
  uses_continuous_medication: null,
  continuous_medication_description: null,
  continuous_medication_instructions: null,
  individualized_nutritional_need: null,
  nutritional_need_details: null,
  health_notes: null,
};

export const normalizeHealthProfile = (profile = {}) => ({
  ...EMPTY_HEALTH_PROFILE,
  ...profile,
});

export const triStateToInput = value => {
  if (value === true) return 'true';
  if (value === false) return 'false';
  return '';
};

export const inputToTriState = value => {
  if (value === 'true') return true;
  if (value === 'false') return false;
  return null;
};

export const normalizeHealthPayloadForSave = profile => {
  const result = normalizeHealthProfile(profile);
  if (result.has_allergies !== true) result.allergies_description = null;
  if (result.has_comorbidities !== true) result.comorbidities_description = null;
  if (result.uses_continuous_medication !== true) {
    result.continuous_medication_description = null;
    result.continuous_medication_instructions = null;
  }
  if (result.individualized_nutritional_need !== true) {
    result.nutritional_need_details = null;
  }
  return result;
};
