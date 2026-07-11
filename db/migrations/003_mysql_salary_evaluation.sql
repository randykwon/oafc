-- MySQL: employee_salary_db / employee_evaluation_db (2026-07-09 스키마)
-- 임베디드 모드에서는 employee_salary_db.* / employee_evaluation_db.* 로 시뮬레이션된다.

CREATE DATABASE IF NOT EXISTS employee_salary_db;
USE employee_salary_db;

CREATE TABLE IF NOT EXISTS salary_payments (
    salary_id INT,
    employee_no VARCHAR(200),
    pay_month VARCHAR(200),
    base_salary INT,
    position_allowance INT,
    meal_allowance INT,
    transport_allowance INT,
    overtime_pay INT,
    night_shift_pay INT,
    holiday_pay INT,
    bonus INT,
    incentive INT,
    tax_deduction INT,
    insurance_deduction INT,
    pension_deduction INT,
    welfare_deduction INT,
    union_fee INT,
    net_pay INT,
    pay_group VARCHAR(200),
    payment_date VARCHAR(200),
    currency VARCHAR(200)
) COMMENT '임직원 월급/보상 지급 데이터 10년치 (MySQL employee_salary_db)';

CREATE DATABASE IF NOT EXISTS employee_evaluation_db;
USE employee_evaluation_db;

CREATE TABLE IF NOT EXISTS evaluation_scores (
    evaluation_id INT,
    employee_no VARCHAR(200),
    evaluation_year INT,
    evaluation_cycle VARCHAR(200),
    goal_score DECIMAL(8,1),
    competency_score DECIMAL(8,1),
    leadership_score DECIMAL(8,1),
    attitude_score DECIMAL(8,1),
    attendance_score DECIMAL(8,1),
    total_score DECIMAL(8,1),
    grade VARCHAR(200),
    dept_rank INT,
    evaluator_no VARCHAR(200),
    evaluator_comment VARCHAR(200),
    promotion_recommended INT,
    is_final INT,
    finalized_at VARCHAR(200)
) COMMENT '임직원 평가 주기/결과/점수 (MySQL employee_evaluation_db)';
