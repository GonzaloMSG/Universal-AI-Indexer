-- Test SQL
CREATE TABLE Users (
    id INT PRIMARY KEY,
    name VARCHAR(50)
);
GO
SELECT * FROM Users WHERE name = 'John';
