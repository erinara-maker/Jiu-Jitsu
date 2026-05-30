import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { environment } from '../environments/environment';

interface TrainingDay {
  day: string;
  start_time: string;
  end_time: string;
}

interface StudentProfile {
  id: number;
  student_number: string;
  phone: string;
  full_name: string;
  age: number;
  birth_date: string;
  cpf: string;
  address: string;
  neighborhood: string;
  city: string;
  modality: string;
  jiu_jitsu_start_date: string;
  monthly_fee: number;
  payment_day: number;
  pix_key: string;
  academy_whatsapp: string;
  academy_whatsapp_url: string;
  payment_status: string;
  authorization_signed: string;
  scholarship_type: string;
  student_status: string;
  dropout_date: string;
  guardian: {
    name?: string;
    relationship?: string;
    cpf?: string;
    phone?: string;
    secondary_phone?: string;
  };
  medical_info: {
    has_restriction?: string;
    description?: string;
  };
  training_days: TrainingDay[];
}

interface LoginResponse {
  access_token: string;
  role: 'admin';
}

interface AdminStudent {
  id: number;
  student_number: string;
  phone: string;
  full_name: string;
  age: number;
  modality: string;
  monthly_fee: number;
  payment_day: number;
  payment_status: string;
  authorization_signed: string;
  scholarship_type: string;
  student_status: string;
  dropout_date?: string;
}

interface AdminPayment {
  id: number;
  full_name: string;
  amount: number;
  status: string;
  method: string;
  provider: string;
  created_at: string;
  paid_at?: string;
}

interface Teacher {
  id: number;
  name: string;
  cpf: string;
  phone: string;
  class_group: string;
  schedule: TrainingDay[];
}

interface PaymentReminderLink {
  student_number: string;
  student_name: string;
  contact_name: string;
  phone: string;
  due_day: number;
  url: string;
}

interface PaymentReminderResponse {
  date: string;
  reminder_type: 'before' | 'due';
  links: PaymentReminderLink[];
  skipped: number;
}

interface CashFlowEntry {
  id: number;
  entry_type: 'entrada' | 'saida';
  description: string;
  category: string;
  payment_method: string;
  amount: number;
  entry_date: string;
  notes: string;
  created_at: string;
}

interface CashFlowResponse {
  month: string;
  summary: {
    income: number;
    expense: number;
    balance: number;
  };
  entries: CashFlowEntry[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  private apiUrl = environment.apiUrl;
  academyWhatsapp = '(88) 9993632214';
  academyWhatsappUrl = 'https://wa.me/55889993632214';
  cashFlowCategories = {
    entrada: ['mensalidade', 'matricula', 'produto', 'aula particular', 'evento', 'outros recebimentos'],
    saida: ['professor', 'aluguel', 'agua/luz/internet', 'material de limpeza', 'manutencao', 'marketing', 'taxas', 'reembolso', 'outros gastos']
  };

  registerData = {
    phone: '',
    full_name: '',
    age: 16,
    birth_date: '',
    cpf: '',
    address: '',
    neighborhood: '',
    city: '',
    modality: 'kid',
    jiu_jitsu_start_date: '',
    monthly_fee: 150,
    payment_day: 10,
    guardian_name: '',
    guardian_relationship: '',
    guardian_cpf: '',
    guardian_phone: '',
    guardian_secondary_phone: '',
    medical_restriction: 'nao',
    medical_restriction_description: ''
  };

  loginData = {
    username: '',
    password: ''
  };

  selectedTrainingDays: Record<string, boolean> = {
    Segunda: true,
    Terca: false,
    Quarta: true,
    Quinta: false,
    Sexta: true,
    Sabado: false
  };

  trainingTimes = {
    start_time: '19:00',
    end_time: '20:30'
  };

  profile?: StudentProfile;
  selectedStudent?: StudentProfile;
  selectedTeacher?: Teacher;
  adminStudents: AdminStudent[] = [];
  adminPayments: AdminPayment[] = [];
  dropoutStudents: AdminStudent[] = [];
  teachers: Teacher[] = [];
  cashFlowEntries: CashFlowEntry[] = [];
  cashFlowSummary = {
    income: 0,
    expense: 0,
    balance: 0
  };
  paymentReminderLinks: PaymentReminderLink[] = [];
  paymentReminderDate = '';
  cashFlowMonth = new Date().toISOString().slice(0, 7);
  userRole = localStorage.getItem('jj_role') || '';
  token = localStorage.getItem('jj_token') || '';
  message = '';

  teacherForm = {
    name: '',
    cpf: '',
    phone: '',
    class_group: 'jiu-jitsu',
    schedule: [
      { day: 'Segunda', start_time: '18:00', end_time: '19:00' }
    ]
  };

  cashFlowForm = {
    entry_type: 'entrada' as 'entrada' | 'saida',
    description: '',
    category: 'mensalidade',
    payment_method: 'pix',
    amount: 0,
    entry_date: new Date().toISOString().slice(0, 10),
    notes: ''
  };

  constructor(private http: HttpClient) {
    if (this.token && this.userRole === 'admin') {
      this.loadAdmin();
    }
  }

  register(): void {
    this.message = '';
    const training_days = Object.entries(this.selectedTrainingDays)
      .filter(([, selected]) => selected)
      .map(([day]) => ({
        day,
        start_time: this.trainingTimes.start_time,
        end_time: this.trainingTimes.end_time
      }));

    this.http.post(`${this.apiUrl}/students`, {
      ...this.registerData,
      training_days
    }).subscribe({
      next: () => {
        this.message = 'Cadastro criado com sucesso.';
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível cadastrar.'
    });
  }

  login(): void {
    this.authenticate(this.loginData);
  }

  private authenticate(credentials: { username: string; password: string }): void {
    this.message = '';
    this.http.post<LoginResponse>(`${this.apiUrl}/login`, credentials).subscribe({
      next: (response) => {
        this.token = response.access_token;
        this.userRole = response.role;
        localStorage.setItem('jj_token', this.token);
        localStorage.setItem('jj_role', response.role);
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Login invalido.'
    });
  }

  copyPixKey(): void {
    const pixCode = this.profile?.pix_key;
    if (!pixCode) {
      return;
    }

    navigator.clipboard.writeText(pixCode).then(() => {
      this.message = 'Código Pix copiado.';
    }).catch(() => {
      this.message = 'Não foi possível copiar o código Pix.';
    });
  }

  loadAdmin(): void {
    const headers = { Authorization: `Bearer ${this.token}` };
    this.http.get<AdminStudent[]>(`${this.apiUrl}/admin/students`, { headers }).subscribe({
      next: (students) => this.adminStudents = students,
      error: () => this.logout()
    });
    this.http.get<AdminPayment[]>(`${this.apiUrl}/admin/payments`, { headers }).subscribe({
      next: (payments) => this.adminPayments = payments
    });
    this.http.get<AdminStudent[]>(`${this.apiUrl}/admin/dropouts`, { headers }).subscribe({
      next: (students) => this.dropoutStudents = students
    });
    this.http.get<Teacher[]>(`${this.apiUrl}/admin/teachers`, { headers }).subscribe({
      next: (teachers) => this.teachers = teachers
    });
    this.loadCashFlow();
  }

  loadCashFlow(): void {
    this.http.get<CashFlowResponse>(`${this.apiUrl}/admin/cash-flow?month=${this.cashFlowMonth}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: (cashFlow) => {
        this.cashFlowSummary = cashFlow.summary;
        this.cashFlowEntries = cashFlow.entries;
        this.cashFlowMonth = cashFlow.month;
      }
    });
  }

  formatModality(modality: string): string {
    const labels: Record<string, string> = {
      kid: 'Kid',
      'kid +': 'Kid +',
      juvenil: 'Juvenil',
      'jiu-jitsu': 'Jiu-Jitsu',
      'jiu-jitsu feminino': 'Jiu-Jitsu feminino',
      boxe: 'Boxe'
    };
    return labels[modality] || modality;
  }

  formatOption(value: string): string {
    const labels: Record<string, string> = {
      nao: 'Não',
      sim: 'Sim'
    };
    return labels[value] || value;
  }

  formatMoney(value: number): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value || 0);
  }

  formatCashFlowType(type: 'entrada' | 'saida'): string {
    return type === 'entrada' ? 'Entrada' : 'Saída';
  }

  formatPaymentMethod(method: string): string {
    const labels: Record<string, string> = {
      pix: 'Pix',
      dinheiro: 'Dinheiro',
      cartao: 'Cartão',
      transferencia: 'Transferência',
      outro: 'Outro'
    };
    return labels[method] || method;
  }

  onCashFlowTypeChange(): void {
    this.cashFlowForm.category = this.cashFlowCategories[this.cashFlowForm.entry_type][0];
  }

  displayPhone(phone?: string): string {
    if (!phone || phone.includes('@')) {
      return 'Não informado';
    }
    return phone;
  }

  addTeacherSchedule(): void {
    this.teacherForm.schedule.push({ day: 'Segunda', start_time: '18:00', end_time: '19:00' });
  }

  removeTeacherSchedule(index: number): void {
    if (this.teacherForm.schedule.length === 1) {
      return;
    }
    this.teacherForm.schedule.splice(index, 1);
  }

  openTeacherDetails(teacher: Teacher): void {
    this.selectedTeacher = teacher;
  }

  closeTeacherDetails(): void {
    this.selectedTeacher = undefined;
  }

  shouldShowGuardian(): boolean {
    return this.calculatedAge() < 18;
  }

  syncAgeFromBirthDate(): void {
    const age = this.calculatedAge();
    if (age >= 0) {
      this.registerData.age = age;
    }
  }

  private calculatedAge(): number {
    const birthDate = this.registerData.birth_date;
    if (birthDate) {
      const birth = new Date(`${birthDate}T00:00:00`);
      if (!Number.isNaN(birth.getTime())) {
        const today = new Date();
        let age = today.getFullYear() - birth.getFullYear();
        const hadBirthday =
          today.getMonth() > birth.getMonth() ||
          (today.getMonth() === birth.getMonth() && today.getDate() >= birth.getDate());
        if (!hadBirthday) {
          age -= 1;
        }
        return age;
      }
    }
    return Number(this.registerData.age);
  }

  openStudentDetails(studentId: number): void {
    this.http.get<StudentProfile>(`${this.apiUrl}/admin/students/${studentId}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: (student) => this.selectedStudent = student,
      error: (error) => this.message = error.error?.detail || 'Não foi possível carregar o aluno.'
    });
  }

  closeStudentDetails(): void {
    this.selectedStudent = undefined;
  }

  saveStudentAdminInfo(): void {
    if (!this.selectedStudent) {
      return;
    }

    this.http.patch(`${this.apiUrl}/admin/students/${this.selectedStudent.id}/admin-info`, {
      authorization_signed: this.selectedStudent.authorization_signed,
      scholarship_type: this.selectedStudent.scholarship_type
    }, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Dados do aluno atualizados.';
        this.openStudentDetails(this.selectedStudent!.id);
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível atualizar o aluno.'
    });
  }

  markDropout(student: StudentProfile): void {
    const confirmed = window.confirm(`Marcar ${student.full_name} como desistente?`);
    if (!confirmed) {
      return;
    }

    this.http.patch(`${this.apiUrl}/admin/students/${student.id}/dropout`, {}, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Aluno movido para a lista de desistentes.';
        this.closeStudentDetails();
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível marcar desistente.'
    });
  }

  reactivateStudent(student: AdminStudent): void {
    this.http.patch(`${this.apiUrl}/admin/students/${student.id}/reactivate`, {}, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Aluno reativado.';
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível reativar o aluno.'
    });
  }

  preparePaymentReminders(reminderType: 'before' | 'due'): void {
    this.message = '';
    this.http.get<PaymentReminderResponse>(
      `${this.apiUrl}/admin/payment-reminders/whatsapp-links?reminder_type=${reminderType}`,
      { headers: { Authorization: `Bearer ${this.token}` } }
    ).subscribe({
      next: (response) => {
        this.paymentReminderLinks = response.links;
        this.paymentReminderDate = response.date;
        const label = reminderType === 'before' ? 'um dia antes' : 'do vencimento';
        this.message = response.links.length
          ? `Lembretes ${label} preparados. Abra os links abaixo para enviar pelo WhatsApp.`
          : `Nenhum aluno pendente encontrado para o lembrete ${label}.`;
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível preparar os lembretes.'
    });
  }

  createCashFlowEntry(): void {
    this.message = '';
    this.http.post(`${this.apiUrl}/admin/cash-flow`, this.cashFlowForm, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Lançamento registrado no fluxo de caixa.';
        this.cashFlowForm.description = '';
        this.cashFlowForm.amount = 0;
        this.cashFlowForm.entry_date = new Date().toISOString().slice(0, 10);
        this.cashFlowForm.notes = '';
        this.loadCashFlow();
      },
      error: (error) => {
        const detail = error.error?.detail;
        this.message = Array.isArray(detail)
          ? detail.map((item) => item.msg).join(' ')
          : detail || 'Não foi possível registrar o lançamento.';
      }
    });
  }

  deleteCashFlowEntry(entry: CashFlowEntry): void {
    const confirmed = window.confirm(`Excluir lançamento "${entry.description}"?`);
    if (!confirmed) {
      return;
    }

    this.http.delete(`${this.apiUrl}/admin/cash-flow/${entry.id}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Lançamento excluído.';
        this.loadCashFlow();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível excluir o lançamento.'
    });
  }

  createTeacher(): void {
    this.message = '';
    this.http.post(`${this.apiUrl}/admin/teachers`, {
      name: this.teacherForm.name,
      cpf: this.teacherForm.cpf,
      phone: this.teacherForm.phone,
      class_group: this.teacherForm.class_group,
      schedule: this.teacherForm.schedule
    }, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Professor cadastrado.';
        this.teacherForm.name = '';
        this.teacherForm.cpf = '';
        this.teacherForm.phone = '';
        this.teacherForm.schedule = [{ day: 'Segunda', start_time: '18:00', end_time: '19:00' }];
        this.loadAdmin();
      },
      error: (error) => {
        const detail = error.error?.detail;
        this.message = Array.isArray(detail)
          ? detail.map((item) => item.msg).join(' ')
          : detail || 'Não foi possível cadastrar professor.';
      }
    });
  }

  deleteTeacher(teacher: Teacher): void {
    const confirmed = window.confirm(`Excluir professor ${teacher.name}?`);
    if (!confirmed) {
      return;
    }

    this.http.delete(`${this.apiUrl}/admin/teachers/${teacher.id}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Professor excluído.';
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível excluir professor.'
    });
  }

  deleteStudent(student: AdminStudent): void {
    const confirmed = window.confirm(`Deseja excluir o aluno ${student.full_name}?`);
    if (!confirmed) {
      return;
    }

    this.http.delete(`${this.apiUrl}/admin/students/${student.id}`, {
      headers: { Authorization: `Bearer ${this.token}` }
    }).subscribe({
      next: () => {
        this.message = 'Aluno excluído com sucesso.';
        if (this.selectedStudent?.id === student.id) {
          this.closeStudentDetails();
        }
        this.loadAdmin();
      },
      error: (error) => this.message = error.error?.detail || 'Não foi possível excluir o aluno.'
    });
  }

  logout(): void {
    localStorage.removeItem('jj_token');
    localStorage.removeItem('jj_role');
    this.token = '';
    this.userRole = '';
    this.profile = undefined;
    this.selectedStudent = undefined;
    this.selectedTeacher = undefined;
    this.adminStudents = [];
    this.adminPayments = [];
    this.dropoutStudents = [];
    this.teachers = [];
    this.cashFlowEntries = [];
    this.cashFlowSummary = { income: 0, expense: 0, balance: 0 };
    this.paymentReminderLinks = [];
    this.paymentReminderDate = '';
  }
}
