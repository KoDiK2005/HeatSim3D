
#include <iostream>
#include <vector>
#include <string>
#include <cmath>

using Grid3D = std::vector<double>;

// ---- Функции из heat3d.cpp (копия) ----
inline int idx(int i, int j, int k, int NY, int NZ) {
    return i * NY * NZ + j * NZ + k;
}
double computeStableDt(double dx, double dy, double dz, double alpha) {
    double inv = 1.0/(dx*dx) + 1.0/(dy*dy) + 1.0/(dz*dz);
    return 0.4 / (2.0 * alpha * inv);
}
double centerTemp(const Grid3D& T, int NX, int NY, int NZ) {
    return T[idx(NX/2, NY/2, NZ/2, NY, NZ)];
}
double meanTemp(const Grid3D& T) {
    double sum = 0.0;
    for (double v : T) sum += v;
    return sum / (double)T.size();
}
struct Params {
    int nx = 30, ny = 30, nz = 30;
    double alpha = 1.28e-5, t_end = 50000.0;
    int save_every = 500;
};
Params parseArgs(int argc, char* argv[]) {
    Params p;
    for (int i = 1; i < argc - 1; ++i) {
        std::string key(argv[i]), val(argv[i+1]);
        if      (key=="--nx")         { p.nx    = std::stoi(val); ++i; }
        else if (key=="--alpha")      { p.alpha = std::stod(val); ++i; }
        else if (key=="--t_end")      { p.t_end = std::stod(val); ++i; }
    }
    return p;
}

int ok = 0, total = 0;
void check(bool cond, const std::string& name) {
    total++;
    std::cout << (cond ? "  [OK]   " : "  [ФЕЙЛ] ") << name << "\n";
    if (cond) ok++;
}

int main() {
    
    std::cout << " ЧАСТЬ 1. ТЕСТЫ КОРРЕКТНОСТИ (ожидаем OK)\n";
   

    std::cout << "\n-- idx(): перевод 3D-координат в индекс 1D-массива --\n";
    check(idx(0, 0, 0, 5, 5) == 0,   "idx(0,0,0) = 0");
    check(idx(1, 0, 0, 5, 5) == 25,  "idx(1,0,0) = NY*NZ = 25");
    check(idx(0, 1, 0, 5, 5) == 5,   "idx(0,1,0) = NZ = 5");
    check(idx(0, 0, 1, 5, 5) == 1,   "idx(0,0,1) = 1");

    std::cout << "\n-- computeStableDt(): шаг по времени удовлетворяет критерию устойчивости --\n";
    {
        double dx=0.1, dy=0.1, dz=0.1, alpha=1e-5;
        double dt = computeStableDt(dx, dy, dz, alpha);
        double stability = 2*alpha*dt*(1/(dx*dx)+1/(dy*dy)+1/(dz*dz));
        check(dt > 0, "dt > 0 для нормальных входных данных");
        check(stability < 1.0, "критерий Куранта 2*alpha*dt*sum(1/d^2) < 1 выполняется");
    }

    std::cout << "\n-- centerTemp() / meanTemp(): извлечение температур из сетки 3x3x3 --\n";
    {
        Grid3D T = {1,2,3, 4,5,6, 7,8,9,   10,11,12,13,14,15,16,17,18,   19,20,21,22,23,24,25,26,27};
        check(centerTemp(T, 3, 3, 3) == 14.0, "centerTemp на сетке 3x3x3 = 14 (геометрический центр)");
        check(std::abs(meanTemp(T) - 14.0) < 1e-9, "meanTemp({1..27}) = 14 (среднее арифметическое)");
    }

    std::cout << "\n-- parseArgs(): разбор аргументов командной строки --\n";
    {
        char a0[]="heat3d", a1[]="--nx", a2[]="45", a3[]="--alpha", a4[]="8.4e-5";
        char* argv[] = {a0,a1,a2,a3,a4};
        Params p = parseArgs(5, argv);
        check(p.nx == 45, "--nx 45 распознан верно");
        check(std::abs(p.alpha - 8.4e-5) < 1e-12, "--alpha 8.4e-5 распознан верно");
    }

    
    std::cout << " ЧАСТЬ 2. ДЕМОНСТРАЦИЯ НАЙДЕННЫХ ОШИБОК\n";
    std::cout << " (это не 'проваленные тесты' — тест специально\n";
    std::cout << "  воспроизводит дефект и подтверждает его наличие)\n";
    

    std::cout << "\n-- Дефект №1: meanTemp() на пустом массиве --\n";
    {
        Grid3D empty;
        double m = meanTemp(empty);
        std::cout << "  meanTemp({}) = " << m << "\n";
        std::cout << "  ПРОБЛЕМА: получаем NaN (деление 0.0/0), нет проверки на пустой контейнер,\n";
        std::cout << "  ошибка нигде не сообщается — NaN тихо ушёл бы дальше по программе.\n";
        check(std::isnan(m), "подтверждено: результат NaN, а не сообщение об ошибке");
    }

    std::cout << "\n-- Дефект №2: parseArgs() падает на нечисловом значении параметра --\n";
    {
        char a0[]="heat3d", a1[]="--nx", a2[]="abc";
        char* argv[] = {a0,a1,a2};
        bool crashed = false;
        std::string reason;
        try {
            parseArgs(3, argv);
        } catch (const std::exception& e) {
            crashed = true;
            reason = e.what();
        }
        std::cout << "  Вызов: heat3d.exe --nx abc\n";
        std::cout << "  ПРОБЛЕМА: std::stoi(\"abc\") бросает исключение (" << reason << "),\n";
        std::cout << "  которое в main() ничем не перехватывается -> программа аварийно завершится\n";
        std::cout << "  (crash), а не покажет пользователю понятное сообщение об ошибке ввода.\n";
        check(crashed, "подтверждено: некорректный ввод приводит к необработанному исключению");
    }

    std::cout << "\n-- Дефект №3: последний флаг без значения молча игнорируется --\n";
    {
        char a0[]="heat3d", a1[]="--t_end", a2[]="9000", a3[]="--nx"; // забыли значение для --nx
        char* argv[] = {a0,a1,a2,a3};
        Params p = parseArgs(4, argv);
        std::cout << "  Вызов: heat3d.exe --t_end 9000 --nx   (забыли указать число после --nx)\n";
        std::cout << "  Результат: p.nx = " << p.nx << " (значение по умолчанию, а не ошибка)\n";
        std::cout << "  ПРОБЛЕМА: цикл разбора (i < argc-1) не проверяет последний аргумент,\n";
        std::cout << "  флаг без значения молча отбрасывается без единого предупреждения.\n";
        check(p.nx == 30, "подтверждено: --nx без значения проигнорирован без сообщения об ошибке");
    }

    
    std::cout << " ИТОГО: " << ok << " / " << total << " проверок подтвердили ожидаемое поведение\n";
    
    return 0;
}
