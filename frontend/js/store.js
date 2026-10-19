/* Tiny shared state: the patient list and the currently selected patient. */

import { api } from "./api.js";

const listeners = new Set();

export const store = {
  patients: [],
  loaded: false,
  selectedPatientId: "",
  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  emit() {
    for (const fn of listeners) fn(this);
  },
  async refreshPatients() {
    this.patients = await api.listPatients();
    this.loaded = true;
    this.emit();
    return this.patients;
  },
  async addPatient(name) {
    const patient = await api.createPatient(name);
    this.patients = [patient, ...this.patients];
    this.emit();
    return patient;
  },
  select(id) {
    this.selectedPatientId = id || "";
    this.emit();
  },
  patientName(id) {
    return this.patients.find((p) => p.id === id)?.name || "";
  },
};
